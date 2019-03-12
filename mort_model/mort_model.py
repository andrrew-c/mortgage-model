print("{0}\nIDEA: Have a repeat deal so that a 2 year fixed ends, the new rate has incremented by trackIncrement and then you're in a new deal{0}".format("*"*100))
import os, sys
import sqlite3
import pandas as pd
import numpy as np

from re import sub
from datetime import datetime

import pdb

## Name of BTL database
db = 'mortgages_btl.db'

## Rate changes (types)
rateTypes = {'Fixed':0, 'Tracker':1, 'Discount':1, 'Stanadrd Variable Rate': 1}

"""Think these should be moved"""
## Total amount to pay a mortgage
modelOverpay = 743          ## A minimum amount the mortgage payment has to be.  If capital payments are below this, the payments will be up to this amount

## If we force overpayments, how much do we pay?
modelOverpayForce = 343     ## If we force mortgage overpayments in the scenario, by how much?


## Number of detailed outputs (i.e. monthly) to be written out to a file
iMaxDetailedOutputs = 10

##################################################################################
## This defines the regularity of the overpayments
## - None, means we do not make any overpayments;
## - Monthly every month by a regular amount defined by Overpay
## - Annual, the regular amomunt is saved up and then paid on the 12th month
##################################################################################

## overPayType
overpayPeriod = {'None': None, 'Monthly': 1, 'Annual': 12}

## Property information

PropertyPrice = 170000
InitialLoan = 99000
MortTerm = 30 #17 + (11/12)

## Inputs to compare different mortgages
mortInputs = [{'PropertyPrice':170000, 'InitialLoan':99000, 'MortTerm':30, 'Overpay':False, 'OverpayForce':False, 'inputLoc':593}, 
                  {'PropertyPrice':500000, 'InitialLoan':445000, 'MortTerm':24, 'Overpay': False, 'OverpayForce':False, 'inputLoc':236}, 
                  {'PropertyPrice':170000, 'InitialLoan':99000, 'MortTerm':30, 'OverpayForce':True, 'overpayPeriod':'Monthly', 'OverpayTypeDiff':False, 'inputLoc':593}, 
                  {'PropertyPrice':500000, 'InitialLoan':445000, 'MortTerm':24, 'OverpayForce':True, 'overpayPeriod':'Monthly', 'OverpayTypeDiff':False, 'inputLoc':236},
                  {'PropertyPrice':170000, 'InitialLoan':99000, 'MortTerm':30, 'OverpayForce':True, 'overpayPeriod':'Annual', 'OverpayTypeDiff':False, 'inputLoc':593}, 
                  {'PropertyPrice':500000, 'InitialLoan':445000, 'MortTerm':24, 'OverpayForce':True, 'overpayPeriod':'Annual', 'OverpayTypeDiff':False, 'inputLoc':236}
              ]

mortInputs = [{'PropertyPrice':500000, 'InitialLoan':445000, 'MortTerm':24, 'Overpay': False, 'inputLoc':236}, 
              {'PropertyPrice':500000, 'InitialLoan':445000, 'MortTerm':24, 'Overpay': True, 'OverpayForce':True, 'overpayPeriod':'Monthly', 'inputLoc':236} ,
              {'PropertyPrice':500000, 'InitialLoan':445000, 'MortTerm':24, 'Overpay': True, 'OverpayForce':True, 'overpayPeriod':'Annual', 'inputLoc':236} ,
              {'PropertyPrice':170000, 'InitialLoan':99000, 'MortTerm':30, 'Overpay': False, 'inputLoc':593},
              {'PropertyPrice':170000, 'InitialLoan':99000, 'MortTerm':30, 'Overpay': True, 'OverpayForce':True, 'overpayPeriod':'Monthly', 'inputLoc':593}
                  
              ]

###############################
## Custom functions
###############################

## Mortgage payment calculator
pmt = lambda r, pv, n: -((r/12)*pv)/(1 - (1+r/12)**(-n))
strecode = lambda afs: float(sub(r'[^\d.]', '', afs))
ltv = lambda loan, price: loan/price

#################################
## Model parameters
#################################

## Number of years to model over
modelYears = 5

## How often tracker rates increase (months)
trackIncrease = 6           ## A tracker product will increment by a certain amount every x months

## How much tracker rate increases by
trackIncrement = 0.0025      ## Tracker, discounted and SVR rates will increase by this amount every trackIncreaseMonths


## Bring together all model parameters
modelParams = {'modelYears':modelYears, 'trackIncrease':trackIncrease, 'trackIncrement':trackIncrement, 'modelOverpay':modelOverpay, 'modelOverpayForce':modelOverpayForce} 

################################################
## Start defining model functions
################################################

## Get mortgage inputs from DB
def getMortInputs(c):
    """
    Returns the results of a sql query (hard-coded in function)
    Inputs -
        c: sqlite3 connection cursor
    """
               
    ## Define dataset
    inputColumns = "LenderName RateType ArrangementFeeString InitialRate InitialPeriod OngoingRate timestamp".split()

    sql  = """
                SELECT {}
                FROM mortgage
            """.format(','.join(inputColumns))

    ## Execute and return results
    c.execute(sql)
    results = c.fetchall()

    ## Create data frame from results
    data1 = pd.DataFrame(results, columns=inputColumns)

    ## Re-code arrangement fee string (afs) into float
    data1['ArrangementFee'] = data1['ArrangementFeeString'].apply(strecode)
    return data1


        
## Set up model dataframe
def setUpModel():
    """ Create a pandas dataframe which holds all of the model information for a single run (the engine)
    """
    columns = "Month RemainingTerm DealNum PropertyPrice Loan LTV InterestRate InterestDue CapitalPaymentDue Fees CapitalPaid OverpaymentPaid FeePaid".split()
    model = pd.DataFrame(None, index=np.arange(modelYears*12+1), columns=columns)
    return model

def month0(model, mortInputs, modelInput):
    """
        Set up month zero of model
    """
    Month = 0

    
    
    ## Create copy of object for ease
    thisMonth = model.iloc[Month]
    thisMonth.Month = Month

    if modelInput.RateType == 'Fixed':
        thisMonth.DealNum = 1

    ## Property price
    thisMonth.PropertyPrice = mortInputs['PropertyPrice']

    ## Interest, capital and overpayment are all zero
    thisMonth.InterestDue, thisMonth.InterestPaid, thisMonth.CapitalPaid, thisMonth.OverpaymentPaid = 0, 0, 0, 0

    ## Initial loan, LTV
    thisMonth.Loan = mortInputs['InitialLoan']
    thisMonth.LTV = ltv(mortInputs['InitialLoan'], mortInputs['PropertyPrice'])

    ## Interest rate
    thisMonth.InterestRate = modelInput.InitialRate/100

    ## Capital payment due
    thisMonth.CapitalPaymentDue = pmt(thisMonth.InterestRate, thisMonth.Loan, thisMonth.RemainingTerm)
    
    thisMonth.Fees = modelInput.ArrangementFee
    thisMonth.FeePaid = thisMonth.Fees

def updateInterestRate(thisMonth, prevMonth, inputs, modelParams):
    """
        Updates tracker rate by increment every trackIncrease months
        month - integer current month of model
        currentRate - current interest rate for product in the month
        trackIncrease - integer, number of months to increase rate by
    """

    ## Create list holding variable rate names
    varRateList = ['Tracker', 'Standard Variable Rate', 'Discount']

    #######################
    ## Fixed rate product
    #######################

    ## Fixed
    if inputs.RateType == 'Fixed':

        ## Within the deal period
        if thisMonth.Month <= inputs.InitialPeriod:
            thisMonth.InterestRate = prevMonth.InterestRate

        ## Fixed rate, after the initial deal
        elif thisMonth.Month%inputs.InitialPeriod ==1:      ## Stay on SVR for 1 month

            ## Go on SVR for a month!  Why not?
            thisMonth.InterestRate = inputs.OngoingRate/100

        ## Else, we sign up for a new deal
        elif thisMonth.Month%inputs.InitialPeriod ==2:

            ## Increment deal number
            thisMonth.DealNum += 1

            ## Increment the rate
            
            rateIncrease = (inputs.InitialPeriod/modelParams['trackIncrease'])*modelParams['trackIncrement']
            thisMonth.InterestRate = inputs.InitialRate/100 + rateIncrease*(thisMonth.DealNum-1)

            #thisMonth.InterestRate = inputs.OngoingRate/100
            #pdb.set_trace()
        else:
            thisMonth.InterestRate = prevMonth.InterestRate
        
    ##########################
    ## Tracker/Variabble rate
    ##########################

    ## 
    elif inputs.RateType in varRateList:


        ## If month has incremented by x months
        if thisMonth.Month%trackIncrease == 0:
            
            ## Add the increment to the customer rate
            thisMonth.InterestRate = prevMonth.InterestRate + modelParams['trackIncrement']
        
        ## Else, keep the rate
        else:
            thisMonth.InterestRate = prevMonth.InterestRate

def calculateInterest(thisMonth, prevMonth):
    """Interest due = previous end month loan * interest rate/12 """
    thisMonth.InterestDue = prevMonth.Loan * (thisMonth.InterestRate/12)

    
def calculateCapital(thisMonth, prevMonth):
    """ Calculate the capital payment due
        If month == 1 or interest rate changed from previous month, calculate the capital payment due
        """

    ## If month 1, take the 'completion date' value
    if thisMonth.Month == 1:
        thisMonth.CapitalPaymentDue =  prevMonth.CapitalPaymentDue
    
    ## Else, if the interest rate has changed, calculate a new capital payment
    elif thisMonth.InterestRate != prevMonth.InterestRate:
        thisMonth.CapitalPaymentDue =  pmt(thisMonth.InterestRate, prevMonth.Loan, thisMonth.RemainingTerm)

    ## Else, return the previous month capital payment
    else:
        thisMonth.CapitalPaymentDue =  prevMonth.CapitalPaymentDue
    
    
def calculateFees(thisMonth):
    """ Update fees """
    thisMonth.Fees = 0
    thisMonth.FeePaid = thisMonth.Fees

def updateLoan(thisMonth, prevMonth):

    """ Update loan """
    #pdb.set_trace()
    #print(prevMonth.Loan, thisMonth.InterestDue, thisMonth.CapitalPaymentDue, thisMonth.OverpaymentPaid)
    thisMonth.Loan = sum((prevMonth.Loan, thisMonth.InterestDue, thisMonth.CapitalPaymentDue, -thisMonth.OverpaymentPaid))
    thisMonth.LTV = ltv(thisMonth.Loan, thisMonth.PropertyPrice)
    
def updatePropertyPrice(thisMonth, mortInputs):
    """ Update property price
        Suggested improvement: Add increase factor"""
    thisMonth.PropertyPrice = mortInputs['PropertyPrice']
    
def calculateOverpayments(thisMonth, mortInputs, modelParams):
    """
    Derive the overpayment amount, depending on the type of overpayment specified in the mortgage input
    """
    #pdb.set_trace()

    ## Initialise overpayment to zero (also needed to replace previous runs)
    thisMonth.OverpaymentPaid = 0
    
    ## If there are to be overpayments
    if mortInputs['Overpay']:
        ## If the overpayment amount is to be forced
        if mortInputs['OverpayForce']:

            ########################
            ## Monthly or annual?
            ########################
            
            ## If overpyaments to be maid monthly
            if mortInputs['overpayPeriod'] == 'Monthly':
                thisMonth.OverpaymentPaid = modelParams['modelOverpayForce']

            ## Else
            elif mortInputs['overpayPeriod'] == 'Annual' and thisMonth.Month > 1 and thisMonth.Month%12 == 0:
                thisMonth.OverpaymentPaid = modelParams['modelOverpayForce'] * 12
                
        ## Else, if user specififed 'OverpayTypeDiff' - meaning, make up the differce
        elif mortInputs['OverpayTypeDiff']:
            ## If the capital payment is less than the overpayment amount, add it
            if -thisMonth.CapitalPaymentDue < modelParams['modelOverpay']:
                thisMonth.OverpaymentPaid = thisMonth.CapitalPaymentDue + modelParams['modelOverpay'] 
        

    
def ModelEngine(modelParams, mortInputs, modelInput, model):
    
    """
    This is the model engine
    modelParams
    modelInputs
    model
    """
    
    for Month in range((modelYears*12)+1):
        #print(Month)
        
        ## Update model remaining term
        model.iloc[Month].RemainingTerm = MortTerm*12 - Month

    
        ## Completion month
        if Month == 0:

            ## Run month zero logic
            month0(model, mortInputs, modelInput)
        
        else:

            ## Create copies of this and previous month
            thisMonth = model.iloc[Month]
            prevMonth = model.iloc[Month-1]

            ## Set up the month variable
            thisMonth.Month = Month
            thisMonth.DealNum = prevMonth.DealNum

            ## Update property price
            updatePropertyPrice(thisMonth, mortInputs)

            ## Interest rate
            updateInterestRate(thisMonth, prevMonth, modelInput, modelParams)

            ## Interest payment due
            #pdb.set_trace()
            calculateInterest(thisMonth, prevMonth)

            ## Update Capital due
            calculateCapital(thisMonth, prevMonth)

            ## Overpayments
            calculateOverpayments(thisMonth, mortInputs, modelParams)

            ## Fees
            calculateFees(thisMonth)

            ## Update loan
            updateLoan(thisMonth, prevMonth)

            ##  See how much capital was paid off
            thisMonth.CapitalPaid = prevMonth.Loan - thisMonth.Loan

          
def initSummaryOutputs():
    
    """ Create a dataframe to hold the outputs """
    
    columns = "Index, InputParameteres, Lender name, Rate type, Initial rate, Initial Period, Ongoing rate, Ending Loan, Ending LTV, Interest Paid, Capital Paid, Overpayments, Fee, Total costs (excl. capital)".split(', ')
    
    df1 = pd.DataFrame(data=None, columns=columns)
    return df1

def initDetailedOutputs(model, n):

    """ Create a dataframe to hold all of the dataframes (up to a maximum of n"""

    detailedOutputs = pd.DataFrame(data=None, columns=model.columns)
    return detailedOutputs
    
def processOutputs(i, mortInput, outputsCol, inputs, model):
    """ Process outputs
        i - integer index of model run
        mortInput - dictionary of model inputs from user (loan amount, overpayment type, etc)
        outputCol - list with column names
        inputs - mortgage inputs from DB
        model - model
    """
    
    output = pd.DataFrame(data=[[i, str(mortInput), inputs.LenderName, inputs.RateType, inputs.InitialRate, inputs.InitialPeriod, inputs.OngoingRate, model.iloc[len(model)-1].Loan, model.iloc[len(model)-1].Loan/model.iloc[len(model)-1].PropertyPrice, model.InterestDue.sum(), model.CapitalPaid.sum(), model.OverpaymentPaid.sum(), model.FeePaid.sum(), sum([model.InterestDue.sum(), model.FeePaid.sum()])]], columns = outputsCol)
    return output
    
def checkWriteOutputs():
    """ Return boolean to write out outputs based on user input"""

    ## Init final results
    bFinalSummary, bFinalDetailed = False, False


    ## Check for summary outputs
    check = input("Do you want to write out summary outputs? Y/N: ")
    if check.casefold() == 'y':
        bFinalSummary = True
    else:
        raise Exception("Please select Y or N")

    ## Check for detailed outputs
    check = input("Do you want to write out detailed outputs (limit 10)? Y/N: ")
    if check.casefold() == 'y':
        bFinalDetailed = True
    else:
        raise Exception("Please select Y or N")

    ## Final results
    return bFinalSummary, bFinalDetailed
    

def writeOutputs(prefix='outputs', bCheck=None, summary=None):
    
    """ A function to output the results to a file with name 'outputs_YYYYMMDD'.
        preix - prefix of output file
        bCheck - boolean checking whether outputs to be written out
        summary - object to be written tout
    """
    
    ## Write outputs
    if bCheck:
        fname = '{}_{}.txt'.format(prefix, datetime.today().strftime('%Y%m%d'))
        f = open(r'results/{}'.format(fname), 'wt')
        summary.to_csv(f, columns=summary.columns)
        f.close()
        
if __name__ == '__main__':

    

    ## Connect to DB
    con = sqlite3.connect(db)
    c = con.cursor()

    ## Get inputs form mortgage offers
    inputs = getMortInputs(c)
    input0 = inputs.iloc[0]
    
    ## Set up model data frame
    model = setUpModel()

    headerString = "Model parameters = {}".format(str(modelParams))

    ## Ask user if they want to write out outputs
    bWriteOutputsSummary, bWriteOutputsDetailed = checkWriteOutputs()

    ## Set start time
    start = datetime.now()


    ## Initialise the outputs
    summaryOutputs = initSummaryOutputs()
    detailedOutputs = initDetailedOutputs(model, n = iMaxDetailedOutputs)


    ##########################################
    ### Start looping through inputs
    ##########################################
    
    ## Loop through all of the mortgage inputs 
    for m in range(len(mortInputs)):
        print("Running mort input {} of {}".format(m+1, len(mortInputs)))

        ## Pull out index of mortgage input selected by user
        userInputSelection = mortInputs[m]['inputLoc']

        ########################################################
        ## If user wants to run through all the product inputs
        ########################################################
        if userInputSelection == None:
            iNum =input("How many to run out of '{}' model inputs?".format(len(inputs)))
            
            ## If user said nothing, then get all
            if iNum == '':
                iNum = len(inputs)

            ## Else, loop through product inputs
            for i in range(min(len(inputs), int(iNum))):
            
                if i%25 == 0:
                    print("Mort input {}: Running model {} of {} ({:.1%})".format(m, i+1, len(inputs), (i+1)/len(inputs)))
                    thisSummary = processOutputs(i, summaryOutputs.columns, inputs.iloc[i], model)
                    summaryOutputs = summaryOutputs.append(thisSummary)
        #############################################################
        ##  Else, take the product input form the user selection
        #############################################################
        else:
            modelInput = inputs.iloc[userInputSelection]
            print("User wants to run through own inputs.\n")
            print("{}".format("_"*60))
            print("Inputs: {}".format(modelInput))
            
            ## Run model engine
            ModelEngine(modelParams, mortInputs[m], modelInput, model)
                        
            ## Summary for this run
            thisSummary = processOutputs(m, mortInputs[m], summaryOutputs.columns, modelInput, model)

            ## Update all summary
            summaryOutputs = summaryOutputs.append(thisSummary)

            ## If user wants detailed outputs
            if bWriteOutputsDetailed and m <= iMaxDetailedOutputs:
                modeltemp = model.copy()
                modeltemp['num'] = m
                detailedOutputs = pd.concat((detailedOutputs, modeltemp))
                del(modeltemp)
                #pdb.set_trace()
                
        
        print("Finished running took {} seconds".format((datetime.now() - start).seconds))

    ## Sort data
    sortedData = summaryOutputs.sort_values(['Total costs (excl. capital)', 'Ending Loan', 'Capital Paid'], ascending=[True, True, False])

    writeOutputs('outputs', bWriteOutputsSummary, sortedData)
    writeOutputs('outputs_detailed', bWriteOutputsDetailed, detailedOutputs)
    


    
        

    
    
    
    
            
            
            
            

