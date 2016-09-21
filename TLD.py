
# coding: utf-8

# In[1]:

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import re
import os


# In[2]:

import glob


# In[3]:

from Matrix import Matrix
from AuxFunctions import *


# In[4]:

class TLD(pd.DataFrame):
    '''A Trip-length distribution DataFrame. Distance is index.
    Columns for time periods, segments, vehicles, etc.'''
    
    @property
    def _constructor(self):
        '''TLD operations return TLD objects.'''
        return TLD
    
    @staticmethod
    def nband(n):
        '''
        Returns a function that returns the corresponding n_band for x
        nband is a wrapper that parametrises n for a banding function
        Useful for pandas.groupby(nband(n))

        >>> [nband(2)(x) for x in range(7)]
        [0, 0, 2, 2, 4, 4, 6]
        '''
        return lambda x: int(x/n)*n
    
    def set_zero(self, inplace=True):
        '''Add initial zero value'''
        if inplace:
            self.at[0,:]=0
        else:
            df = self.copy()
            df.at[0,:]=0
            return df

    def band_agg(self, n, current_bands=0):
        '''Aggregates to bands of n.
        current_bands - length of the interval. 0 to estimate it.'''
        
        if not current_bands:
            current_bands = self.index.get_level_values(-1)[1]
        
        if n < current_bands:
            ErrMsg = '''input n ({}) < TLD band aggregation ({})
                This function cannot be used to disaggregate a TLD'''.format(n, current_bands)
            raise ValueError(ErrMsg)
        
        TLDn = self.groupby(TLD.nband(n)).sum() #TLD by bands
        TLDn = TLD(TLDn) #Groupby does not preserve TLD subclass
        TLDn.index = TLDn.index + n #re-index to top end of each band
        TLDn.set_zero()
        return TLDn.sort_index()
    
    #TODO: Should this return a copy?
    def normalize(self):
        '''Normalizes TLD so TLD will contain proportion of trips 
        for each distance band rather thab absolute number of trips.'''
        return self.apply(lambda x: x / x.sum())
    
    @property
    def norm(self):
        return self.normalize()
    
    def mid_band(self, level=0, factor=0.5, current_bands=0, inplace=False):
        '''Re-index to the medium point of the interval.
        level         - index level to use
        factor        - factor to apply to the interval
        current_bands - length of the interval. 0 to estimate it.'''
        
        if inplace:
            df = self
        else:
            df = self.copy()

        idx = df.index

        if not current_bands:
            idx_increments = idx.get_level_values(level) - pd.Series(idx.get_level_values(level)).shift()
            idx_increments = pd.Series(idx_increments).dropna()
            current_bands = min(idx_increments)

        reidx = idx + current_bands * factor
        
        df.index = reidx

        if not inplace:
            return df
        
    def trim_index(self, index_names_to_keep='from', inplace=False):
        '''Wrapper for trim_index_df, adapted for TLD.'''
        return trim_index_df(self, index_names_to_keep, inplace)
    
    def to_numeric(self):
        '''Converts strings into numbers.'''
        tmp_index_names = self.index.names
        self.index = pd.to_numeric(TLD.index)
        self.index.names = tmp_index_names #I can't remmeber now why this is necessary
        return self.apply(lambda x: pd.to_numeric(x))
    
    def truncate(self, dist):
        '''Truncates based on the index values.'''
        return self.loc[self.index < dist]
    
    @property
    def avgdist(self, level=-1):
        '''Returns the average distances (weighted average, SUMPRODUCT)
        of the TLD columns. TLD should contain totals, not proportions.'''
        return self.apply(lambda x: (x * self.index.get_level_values(level)).sum())
    
    ##TODO: Add an option to dropna of fillna
    @staticmethod
    def from_dist_col(mat, dist_col=-1, dist_band=1, normalized=False):
        '''Returns the Trip-Lenght Distribution of mat, 
        based on dist_col, aggregated by dist_band.'''

        if isinstance(dist_col, int):
            dist_col = mat.columns[dist_col]

        tld = mat.copy()
        tld.ix[:,dist_col] = tld.ix[:,dist_col].apply(TLD.nband(dist_band))

        tld = tld.groupby(by=dist_col).sum()
        tld.index = tld.index + dist_band #top end of each band
        tld.at[0,:]=0 #fill initial zero value

        tld = tld.sort_index()
        
        tld = TLD(tld)
        
        if normalized:
            tld = tld.norm
            
        return tld

    @staticmethod
    def from_mat_single(mat, dist, dist_col=-1, dist_band=1, normalized=False):
        '''Returns the Trip-Lenght Distribution of mat, 
        based on distance (dist_col) form dist, aggregated by dist_band.
        mat can have any number of culumns, but only dist_col will be used
        for the TLD. dist_col admits integer and column name.'''

        if isinstance(dist_col, int):
            dist_col = dist.columns[dist_col]

        df = mat.join(dist.ix[:,[dist_col]]).fillna(0)
        tld = TLD.from_dist_col(df, dist_col, dist_band)
        
        tld = TLD(tld)
        
        if normalized:
            tld = tld.norm
        
        return tld
    
    @staticmethod
    def from_mat(mat, dist, dist_band=1, normalized=False):
        '''Returns the Trip-Length Distribution of mat.
        TLD for each mat column will be based on the corresponding
        column from dist (in order). mat and dist must have the same
        number of columns, or just the first distance column will be
        used.'''

        if len(mat.columns) != len(dist.columns):
            return TLD.from_mat_single(mat, dist, dist_band=dist_band, normalized=normalized)

        dfs = zip_df_cols([mat,dist])
        TLDs = [TLD.from_dist_col(df, dist_col=1,
                                    dist_band=dist_band,
                                    normalized=normalized)
                for df in dfs]

        tld = pd.DataFrame()
        for xtld in TLDs:
            tld = pd.concat([tld, xtld], axis=1)

        tld = TLD(tld)
        
        if normalized:
            tld = tld.norm 

        return tld
    
    @staticmethod
    def read_EMME_TLD(file):
        '''Returns TLD df from an EMME TLD report file, with columns:
        ['from','to','density_abs','density_norm','cumulative_abs','cumulative_norm']
        '''

        # EMME_TLD_cols - in order, position matters
        EMME_TLD_cols = ['from','to','density_abs','density_norm','cumulative_abs','cumulative_norm']

        idx_cols = EMME_TLD_cols[:2]
        data_cols = EMME_TLD_cols[2:]

        # RegEx to read EMME format:
        NumberPat = r'-?\.?\d*\.?\d+'
        TLDRowPat = r'(?<=\n)\s*({0})\s+({0})\s+({0})\s+({0})\s+({0})\s+({0})'
        EMMErecord_re = re.compile(TLDRowPat.format(NumberPat))

        # Read data
        with open(file, 'r') as f:
            f_content = f.read()
            data = EMMErecord_re.findall(f_content)

        # Convert data to DataFrame
        df = pd.DataFrame.from_records(data,
                                       columns=EMME_TLD_cols,
                                       index=idx_cols)
        return df
    
    @staticmethod
    def read_EMME_TLDs(files):
        '''Reads all TLD reports specified in files
        and returns four DataFrames, with the TLDs combined.
        Recomended: use glob to get the list of files from a pattern.
        Returns one DataFrame for each of the TLD EMME columns:
        ['density_abs','density_norm','cumulative_abs','cumulative_norm']
        '''
        TLDs = [read_EMME_TLD(file) for file in files]
        combinedTLDs = list(PairWiseColumnGroups(TLDs))

        filenames = [os.path.basename(file) for file in files]
        for tld in combinedTLDs:
            tld.columns = filenames
        density_abs, density_norm, cumulative_abs, cumulative_norm = combinedTLDs

        return density_abs, density_norm, cumulative_abs, cumulative_norm
    
    #TODO: Set xmax, ymax for x and y axes
    def to_JPG(self, OutputName='TLD.png', title='Trip-Length Distribution',
                   ylabel='Trips', units='',
                   legend=False, table_font_colors=True,
                   prefixes='', suffixes='',
                   *args, **kwargs):
        '''Produces a graph from TLD, all columns together.
        Includes average distance.
            prefixes         - to prepend to each column. Use as a marker.
            suffixes         - to append to each column. Use as a marker.
        '''

        if prefixes:
            try:
                self.columns = [prefix+col for col,prefix in zip(self.columns,prefixes)]
            except:
                raise ValueError("prefixes must have the same length as df.columns.")

        if suffixes:
            try:
                self.columns = [col+sufix for col,sufix in zip(self.columns,suffixes)]
            except:
                raise ValueError("suffixes must have the same length as df.columns.")

        if duplicates_in_list(self.columns):
            raise ValueError("Duplicate names in DataFrame's columns.")

        plt.clf()
        axs_subplot = self.plot(title=title, legend=legend)
        line_colors = [line.get_color() for line in axs_subplot.lines]

        if legend:
            lgd = plt.legend(loc='upper center', bbox_to_anchor=(0.5, -0.1),
                              fancybox=True, ncol=len(TLD.columns))
        plt.xlabel('Dist')
        plt.ylabel(ylabel)

        if units:
            col_label = 'Avg Dist ({})'.format(units)
        else:
            col_label = 'Avg Dist'

        table = plt.table(
            cellText=[['{:,.2f}'.format(dist)] for dist in list(self.avgdist)],
            colWidths = [0.1],
            rowLabels=[' {} '.format(col) for col in self],
            colLabels=[col_label],
            loc='upper right')
        #table.set_fontsize(16)
        table.scale(2, 2)

        if table_font_colors:
            for i in range(len(line_colors)):
                #table.get_celld()[(i+1, -1)].set_edgecolor(line_colors[i])
                table.get_celld()[(i+1, -1)].set_text_props(color=line_colors[i])

        oName = OutputName
        plt.savefig(oName, bbox_inches='tight')
        plt.close()
        
    def cols_to_JPGs(self, oFileNamePattern='TLD_{}.png', *args, **kwargs):
        '''Produces a graph for each column of TLD.
        Names based on oFileNamePattern and column names.
        Includes average distance.'''
        for col in self:
            oFname = oFileNamePattern.format(col)
            self[[col]].to_JPG(oFname, *args, **kwargs)
            
    #TODO: output average distances as DataFrame (and export as csv?)
    @staticmethod
    def comparison_to_JPGs(TLDs, oFileNamePattern='TLD_{}.png', *args, **kwargs):
        '''Produces comparison graphs of the columns in each TLD in TLDs list.
        Columns are taken pairwise, in positional order.
        Names based on column names.'''
        comparisonTLDs = [TLD(df) for df in zip_df_cols(TLDs)]
        #zip_df_cols produces DataFrames, not TLDs
        for tld in comparisonTLDs:
            tldn = '-'.join(tld.columns)
            OutputName = oFileNamePattern.format(tldn)
            TLD.to_JPG(tld, OutputName, *args, **kwargs)

