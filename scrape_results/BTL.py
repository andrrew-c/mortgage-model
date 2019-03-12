import requests
from bs4 import BeautifulSoup as bs
import json
import pickle
import os
import pdb
from datetime import datetime
import sqlite3
import functions as mf

from selenium import webdriver
from selenium.webdriver.common.keys import Keys


## Type of mortgages we can search for
type_dict = {'btl':'/buy-to-let', 'remo':'/remortgage', 'purchase':'/first-time-buyer'}


########################################################
## Search information
########################################################
mortType = 'purchase'                           ## Needs to be next to URL
propValue = 170000
borrowAmt = 99000
ltv = borrowAmt/propValue
ltvs = "{:.0%}".format(ltv)
term = 23
intOnly = 'false'       ## Interest only

## URL information
url = "https://money.comparethemarket.com/mortgages"
today = datetime.today().strftime('%Y%m%d')     ## Today's timestamp
cur_url = url + type_dict[mortType]             ## URL to search



## Cached information/DB
pickledInfo = 'mort_search_{}_{}_{}'.format(mortType, ltvs, today)
dbname = 'mortgages_{}.db'.format(mortType)

## Payload to query mortgages
payload = {'PropertyValue':propValue, 'BorrowAmount':borrowAmt, 'Term':term, 'IsInterestOnly':intOnly, 'IsRequestFromTool':'true'}

#pdb.set_trace()
def getMortInfo(overwritePickle=False):
        
    ## If pickled information not found
    if not os.path.isfile(pickledInfo) or overwritePickle:

        print("Pickled information not found with name '{}'".format(pickledInfo))
        
        ### Request information
        res = requests.get(cur_url, params=payload)        
        
        #with open('content.txt', 'wb') as f: f.write(res.content)
        soup = bs(res.content, 'html.parser')
        #pdb.set_trace()

        ## Find mortgage data
        mort = soup.find_all('div', id="mortgages-data")

        if len(mort) > 0:
            mort = mort[0]

        ## Extract JSON data
        json_text = mort.text[mort.text.find('['):mort.text.find('}]')+2]
        js_data = json.loads(json_text)

        ## Pickle the info
        with open(pickledInfo, 'wb') as f: pickle.dump(js_data, f)
        
    else:
        print("Loading js_data from pickle with name '{}'".format(pickledInfo))
        with open(pickledInfo, 'rb') as f: js_data = pickle.load(f)

    return js_data
        


## Create DB
def create_table(dbname, dictionary):

    str1 = ''
    str2 = ''

    ## Add any other columns as required
    dictionary[0].update({'timestamp':None, 'ltv':None})
    
    for k in dictionary[0]:
        str1 += "{} STRING,"
        str2 += "{},".format(k)
    ## Remove last comma
    str1 = str1[:len(str1)-1]
    str2 = str2[:len(str2)-1]
        
##    print(str1)
##    print(str2)
##        
    
    sql = """ CREATE TABLE IF NOT EXISTS mortgage
                ({})
            """.format(str1).format(*str2.split(','))

    ## Connect/Create DB
    con = sqlite3.connect(dbname)
    c = con.cursor()
    c.execute(sql)
    con.commit()
    con.close()

def update_table(dbname, dictionary):

    con = sqlite3.connect(dbname)
    c = con.cursor()

    ## Get SQL commands from dictionary
    sql_commands = sql_commands_btl(dictionary, 'mortgage')

    ## Iterate through SQL commands and execute them
    for s in sql_commands:
        if s != None:
            #print(s)
            c.execute(s)
    con.commit()
    con.close()

def sql_commands_btl(dictionary, tablename):

    """ Create insert statements for each record in dictionary list """
    sql_commands = []

    ## Create timestamp for updating DB
    timestamp = datetime.now().strftime('%Y%m%d_%H:%M:%S')

    ## For each record in dictionary list
    for i in range(len(dictionary)):

        dictionary[i].update({'timestamp':timestamp, 'ltv':ltvs})
        #pdb.set_trace()

        ## Init string to blank
        str1 = ''
        str2 = ''
        varnames = list(dictionary[i].keys())
        values = list(dictionary[i].values())

        ## Create space for 
        for k in dictionary[i]:
            str1 += "{},"
            str2 += '"{}",'
        str1 = str1[:len(str1)-1]
        str2 = str2[:len(str2)-1]

        ## For this record, create the SQL command to insert
        sql_into = """ INSERT INTO {} ({})
                        VALUES ({})""".format(tablename, str1, str2).format(*varnames, *values)
        sql_commands.append(sql_into)        
        
    return sql_commands

def dbRanToday(dbname):

    """ Checks the latest time in the DB"""

    ## connect to database
    con = sqlite3.connect(dbname)
    c = con.cursor()
    
    ## Select latest timestamp
    sql = """ SELECT MAX(timestamp) 
                FROM mortgage
                WHERE LTV = "{}"
                
            """.format(ltvs)

    
    ## Execute and get results
    c.execute(sql)
    res = c.fetchone()
    
    ## Get today's today
    today = datetime.today().strftime('%Y%m%d')
    con.close()
    
    
    ## If result is not empty
    if res[0] == None:
        return False
    
    ## If latest timestmap is today
    elif res[0][:len(today)] == today:
        return True

    ## Else, not run
    else:
        return False
  
def clearOldFilesWithPrefix(prefix=''):
    """
    Deletes all files in working folder which match the prefix given
    Where the last 8 characters (YYYYMMDD) are not today
    """

    ## Get list of files in current working directory
    files = os.listdir()

    ## All matches
    matches = [f for f in files if f[:len(prefix)]==prefix]

    # All matches - excluding today
    today = datetime.today().strftime('%Y%m%d')
    oldMatches = [m for m in matches if m[-len(today):]!=today]

    ## Delete all files
    [print("{}".format(i)) for i in oldMatches]
    if len(oldMatches)>0:
        if input('Do you want to delete these {} file(s)?\nY/N? '.format(len(oldMatches))).upper() == 'Y':
            [os.unlink(f) for f in oldMatches]
            print("Files deleted.")

        return oldMatches

if __name__=='__main__':
    js_data = getMortInfo(True)
    create_table(dbname, js_data)
    
    if not dbRanToday(dbname):
        print("DB with name '{}' has not been run today. To be updated".format(dbname))
        update_table(dbname, js_data)
    else:
        print("DB with name '{}' has been run today with LTV='{}'.  NOT TO BE UPDATED".format(dbname, ltvs))
        
#print(__name__)

