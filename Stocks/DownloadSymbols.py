import pandas as pd
import requests
from tqdm import tqdm
from bs4 import BeautifulSoup
from string import ascii_uppercase as uppercase
from datetime import date


# download pair of symbol and company from EODData.
# the URL follow pattern as: url = "https://eoddata.com/stocklist/" + ExchangeName + "/" + alphabet + ".htm"
# where ExchangeName could be any of ["NYSE", "NASDAQ", "AMEX", "USMF"], etc.

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


for ExchangeName in ["NASDAQ", "NYSE"]:
    print(f"Processing Stocks from {ExchangeName}", "\n")
    for i in tqdm(range(len(uppercase))):
        alphabet = uppercase[i]        
        result = get_list_by_exchange_alphabet(eoddata_url, ExchangeName, alphabet)
        master_df = pd.concat([master_df, result])

master_df['DownloadDate'] = str(date.today)


print('\n')
t0 = time()
print('Begin saving Info data to Pickle file compressed by BZ2, ', pd.to_datetime(t0, unit='s'))
filename = 'D:/Temp/data/USMarket/data/US-Symbol-' + str(date.today()) +'.pkl'
df_info.to_pickle(filename, compression='bz2')
t1=time()
print('Finish saving Info file to Pickle, ', pd.to_datetime(t1, unit='s'))
