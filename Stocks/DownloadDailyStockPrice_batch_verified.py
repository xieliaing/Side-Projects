'''
This program download daily level stock prices from Yahoo Finance.
It is scheduled to run every trading day at night.

'''
import requests
import pandas as pd
import yfinance as yf
import numpy as np
from tqdm import tqdm
from datetime import date
from time import time
from tqdm import tqdm
from bs4 import BeautifulSoup
from string import ascii_uppercase as uppercase
import os

Num_Stocks = 4000
''' 
#List of sector names to process
sectors = ['Utility', 'Tech', 'TeleComm', 'RealEstate', 'Industrials', 
           'HealthCare', 'Financial', 'Energy', 'ConsumerStaples', 
           'ConsumerDiscretion', 'BasicMaterials']

# Initialize an empty list to store DataFrames
df_list = []

# Loop through each sector and read the corresponding CSV file downloaded from NASDAQ stock screener on 2024/9/28
for sector in sectors:
    # Construct the filename for the sector
    file_name = f'nasdaq_screener_{sector}.csv'
    
    # Check if the file exists (in case some sectors are missing)
    if os.path.exists(file_name):
        # Read the CSV into a DataFrame
        df = pd.read_csv(file_name)
        
        # Modify the column names to be operation-friendly
        df.columns = df.columns.str.replace('% Change', 'Percent_Change') \
                               .str.replace(' ', '_') \
                               .str.replace('"', '')
        
        # Append the DataFrame to the list
        df_list.append(df)

# Concatenate all the DataFrames in the list into a single DataFrame
stock_list = pd.concat(df_list, ignore_index=True)
''' 
stock_list = pd.read_csv('combined_stock_list_2024_09_28.csv')
print('Finish reading Stock symbol list', '\n')

# Only select the top Num_Stocks by Market Cap to avoid Risks
stock_list = stock_list.sort_values(by='Market_Cap', ascending=False)[:Num_Stocks]


print('\n')
t0 = time()
print(f"Total number of Stocks to download today : {stock_list.shape[0]}")


output_folder = "./data/USMarket/data/"
# output_file = "first_last_by_year.csv"

# Check if the folder exists, if not, create it
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

allhist=pd.DataFrame()
allinfo=pd.DataFrame()
print('\n')

batch_size = 40
symbol_list = stock_list.Symbol 
iteration =  range(0, len(symbol_list), batch_size) 
iter_symbol_batches = [symbol_list[i:i+batch_size] for i in iteration ]

price_master_df = pd.DataFrame()

for _symbols in  iter_symbol_batches :
    stock_tickers= " ".join(_symbols)
    _data= yf.download(tickers = stock_tickers,  # list of tickers
                               period = "max",         # time period
                               interval = "1d",       # trading interval
                               prepost = False,       # download pre/post market hours data?
                               repair = True,         # repair obvious price errors e.g. 100x?
                               auto_adjust=False,
                               #debug = False,
                               progress=True,
                               group_by = "Ticker")
    _data2 = _data.stack(level=0).rename_axis(['Date', 'Ticker']).reset_index(level=1)
    allhist = pd.concat([allhist, _data2])
        
new_columns = [s.lower().replace(" ", "_") for s in allhist.columns]
allhist.columns = new_columns        
allhist.index.name = "date"

print('Downloading completed')
print('\n')
t1 = time()

t_diff1 = t1-t0
if t_diff1<60:
    print('Total time used downloading Stock price hisotry : ', np.round(t_diff1, 2), ' sec')
else:
    t_diff_min = t_diff1/60
    print('Total time used downloading Stock price hisotry : ', np.round(t_diff_min, 1), ' min')
print('\n')

print('Begin saving Price data to Pickle file compressed by BZ2, ', pd.to_datetime(t0, unit='s'))

filename = output_folder + 'Stock-Price-Top-' + str(Num_Stocks) + '-' + str(date.today()) +'.pkl'
allhist.to_pickle(filename, compression='bz2')
t2=time()
print('Finish saving file to Pickle, ', pd.to_datetime(t1, unit='s'))


t_diff2 = t2-t1
if t_diff2<60:
    print('Total time used saving price file : ', np.round(t_diff2, 2), ' sec')
else:
    t_diff_min = t_diff2/60
    print('Total time used saving price file : ', np.round(t_diff_min, 1), ' min')
print('\n')


print('\n')

print('Complete all tasks.')