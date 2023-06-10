'''
This program download daily level stock prices from Yahoo Finance.
It is scheduled to run every trading day at night.

'''
import pandas as pd
import yfinance as yf
import numpy as np
from tqdm import tqdm
from datetime import date
from time import time

tickers = pd.read_csv("d:/temp/data/USMarket/us stock list.csv")
tickers = tickers.loc[(tickers.MarketCap>0) & (tickers.Country=="United States") & (tickers.IPOYear>=0)].copy()
tickers=tickers.reset_index()

# section to download Stock prices
allhist={}
allinfo={}
print('\n')

for i in tqdm(range(tickers.shape[0])):
    if (tickers.Subsector[i]!="n/a"):
        stock = tickers.stock_id[i]
        filename = stock+".csv"
        stock_data = yf.Ticker(stock)
        try:
            info = stock_data.info            
        except:            
            continue
        else:
            hist = stock_data.history(period="5y", debug=False).reset_index()
            allhist[stock] = hist
            allinfo[stock] = info

        
        

for key in allhist.keys():
    allhist[key]['stock'] = key 

df_hist = pd.concat(allhist.values())        
    

for key in allinfo.keys():
    allinfo[key]['stock'] = key 
    if 'dividendDate' in allhist[key].keys():
        allinfo[key]['dividendDate']=pd.to_datetime(allinfo[key]['dividendDate'], unit='s')
        
df_info=pd.DataFrame.from_dict(allinfo, orient='index')    



'''
print('\n')
t0 = time()
print('Begin saving data to CSV compressed using BZ2 method')
filename = 'D:/Temp/data/USMarket/data/US-Price-' + str(date.today()) +'.bz2'
df.to_csv(filename, index=False, compression='bz2')
print('Finish saving to CSV file')
'''

print('\n')
t0 = time()
print('Begin saving Price data to Pickle file compressed by BZ2, ', pd.to_datetime(t0, unit='s'))
filename = 'D:/Temp/data/USMarket/data/US-Price-' + str(date.today()) +'.pkl'
df_hist.to_pickle(filename, compression='bz2')
t1=time()
print('Finish saving file to Pickle, ', pd.to_datetime(t1, unit='s'))

t_diff = t1-t0
if t_diff<60:
    print('Total time used saving price file : ', np.round(t_diff, 2), ' sec')
else:
    t_diff_min = t_diff/60
    print('Total time used saving price file : ', np.round(t_diff_min, 1), ' min')
print('\n')



print('\n')
t0 = time()
print('Begin saving Info data to Pickle file compressed by BZ2, ', pd.to_datetime(t0, unit='s'))
filename = 'D:/Temp/data/USMarket/data/US-Info-' + str(date.today()) +'.pkl'
df_info.to_pickle(filename, compression='bz2')
t1=time()
print('Finish saving Info file to Pickle, ', pd.to_datetime(t1, unit='s'))

t_diff = t1-t0
if t_diff<60:
    print('Total time used saving Info file : ', np.round(t_diff, 2), ' sec')
else:
    t_diff_min = t_diff/60
    print('Total time used saving Info file : ', np.round(t_diff_min, 1), ' min')
print('\n')
