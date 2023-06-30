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


def get_list_by_exchange_alphabet(master_url, exchange, alphabet):
    url =  master_url + exchange + "/" + alphabet + ".htm"
    # set an empty dictionary to keep symbol and company name
    #result = {}
    
    # define composite keys of Exchange+Symbol as tuples
    keys = []
    # define corresponding company name as tuples
    companies = []
    # Send a GET request to the URL
    response = requests.get(url)
    # Create a BeautifulSoup object with the response content
    soup = BeautifulSoup(response.content, "html.parser")
    # Find the table containing the stock information
    table = soup.find("table", {"class": "quotes"})
    # Iterate over each row in the table
    for row in table.find_all("tr"):
        # Extract the cells within the row
        cells = row.find_all("td")
    
        # Ensure the row has cells
        if len(cells) > 0:
            # Extract the stock symbol and name from the cells
            symbol = cells[0].text.strip()
            name = cells[1].text.strip()
            keys.append((exchange, symbol))
            companies.append(name)
            #result.update( { symbol : name } )
    
    keys_df = pd.DataFrame(keys, columns=["Exchange", "Symbol"])
    
    # Create the dictionary using the keys and values
    data_dict = {key: company for key, company in zip(keys, companies)}
    
    # Convert the dictionary to a pandas DataFrame
    df = pd.DataFrame(list(data_dict.items()), columns=["Composite Key", "Company"])
    
    # Merge the keys DataFrame with the values DataFrame
    df = pd.merge(keys_df, df, left_index=True, right_index=True, how="left")
    
    # Drop the redundant composite key column
    df.drop("Composite Key", axis=1, inplace=True)
    
    return( df )

df_symbol = pd.DataFrame(columns=["Exchange", "Symbol", "Company"])
eoddata_url = "https://eoddata.com/stocklist/"

for ExchangeName in ["NASDAQ", "NYSE"]:
    print(f"Processing Stocks from {ExchangeName}", "\n")
    for i in tqdm(range(len(uppercase))):
        alphabet = uppercase[i]        
        result = get_list_by_exchange_alphabet(eoddata_url, ExchangeName, alphabet)
        df_symbol = pd.concat([df_symbol, result])

df_symbol['DownloadDate'] = str(date.today())
df_symbol=df_symbol.reset_index(drop=True)

# for any stock that contains "-" in ticker name, remove it because yahoo finance does not have the data

drop_idx = []
for _i in range(df_symbol.shape[0]):
     ticker = df_symbol.iloc[_i].Symbol
     if ("-" in ticker) | ("." in ticker):
           drop_idx.append(_i)

df_symbol.drop(drop_idx, inplace=True)



print('\n')
t0 = time()
print(f"Total number of stocks to download today : {df_symbol.shape[0]}")
print('Begin saving Symbol data to Pickle file compressed by BZ2, ', pd.to_datetime(t0, unit='s'))
filename = 'D:/Temp/data/USMarket/data/US-Symbol-' + str(date.today()) +'.pkl'
df_symbol.to_pickle(filename, compression='bz2')
t1=time()
print('Finish saving Symbol file to Pickle, ', pd.to_datetime(t1, unit='s'))


'''
tickers = pd.read_csv("d:/temp/data/USMarket/us stock list.csv")
tickers = tickers.loc[(tickers.MarketCap>0) & (tickers.Country=="United States") & (tickers.IPOYear>=0)].copy()
tickers=tickers.reset_index()
'''
# section to download Stock prices using yfinance download method on a batch of tickers:
# yf.download(tickers = "SPY AAPL",  # list of tickers
#             period = "1y",         # time period
#             interval = "1d",       # trading interval
#             prepost = False,       # download pre/post market hours data?
#             repair = True,         # repair obvious price errors e.g. 100x?
#             group_by = "Ticker"

# handling Multi-level columns from batch downloading:
#  https://stackoverflow.com/questions/63107594/how-to-deal-with-multi-level-column-names-downloaded-with-yfinance/63107801#63107801

# iterating symbols through a batch of 5:
# symboles = pd.read_pickle("./data/US-Symbol-2023-06-29.pkl", compression="bz2")
# result = [symbols['Symbol'][i:i+5] for i in range(0, len(symbols), 5)]


allhist=pd.DataFrame()
allinfo=pd.DataFrame()
print('\n')

batch_size = 20
symbol_list = df_symbol.Symbol 
iteration =  range(0, len(symbol_list), batch_size) 
iter_symbol_batches = [symbol_list[i:i+batch_size] for i in iteration ]

price_master_df = pd.DataFrame()

for _symbols in  iter_symbol_batches :
    stock_tickers= " ".join(_symbols)
    _data= yf.download(tickers = stock_tickers,  # list of tickers
                               period = "10y",         # time period
                               interval = "1d",       # trading interval
                               prepost = False,       # download pre/post market hours data?
                               repair = True,         # repair obvious price errors e.g. 100x?
                               auto_adjust=False,
                               debug = False,
                               progress=True,
                               group_by = "Ticker")
    _data2 = _data.stack(level=0).rename_axis(['Date', 'Ticker']).reset_index(level=1)
    allhist = pd.concat([allhist, _data2])
        
new_columns = [s.lower().replace(" ", "_") for s in allhist.columns]
allhist.columns = new_columns        
allhist.index.name = "date"

''' 
for key in allhist.keys():
    allhist[key]['stock'] = key 

df_hist = pd.concat(allhist.values())        
    

for key in allinfo.keys():
    allinfo[key]['stock'] = key 
    if 'dividendDate' in allhist[key].keys():
        allinfo[key]['dividendDate']=pd.to_datetime(allinfo[key]['dividendDate'], unit='s')
        
df_info=pd.DataFrame.from_dict(allinfo, orient='index')    
'''


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
allhist.to_pickle(filename, compression='bz2')
t1=time()
print('Finish saving file to Pickle, ', pd.to_datetime(t1, unit='s'))

t_diff = t1-t0
if t_diff<60:
    print('Total time used saving price file : ', np.round(t_diff, 2), ' sec')
else:
    t_diff_min = t_diff/60
    print('Total time used saving price file : ', np.round(t_diff_min, 1), ' min')
print('\n')


'''
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
'''