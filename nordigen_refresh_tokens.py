
#%%
import requests
import json
import yaml
from dotenv import load_dotenv
from pathlib import Path
import os

dotenv_path = Path('.env')
load_dotenv(dotenv_path=dotenv_path)

#with open(os.path.join(os.getcwd(), os.getenv("NORDIGEN_CONFIG_FILE_PATH"))) as f:
#    print(f.read())

nordigen_config = yaml.load(open(os.path.join(os.getcwd(), os.getenv("NORDIGEN_CONFIG_FILE_PATH"))), Loader=yaml.FullLoader)
# Step 1: Get Access Token
#%%
url = 'https://bankaccountdata.gocardless.com/api/v2/token/new/'
payload = json.dumps(nordigen_config.get("nordigen"))
headers = {'Content-Type': 'application/json', 'accept': 'application/json'}
#%%
r = requests.post(url, data=payload, headers=headers)
# %%
response_parsed = json.loads(r.content)
if "access" not in response_parsed:
    raise Exception("Something went wrong while requesting for new token")
# %%
# Step 2: Choose banks
requests.get(
    "https://bankaccountdata.gocardless.com/api/v2/institutions/?country=pt",
    headers={
        'accept': 'application/json',
        'Authorization': f'Bearer {response_parsed["access"]}'
    }
)


#%% 
# Step 3: Create enduser agreement
SELECTED_BANKS=[
    "BANCOACTIVOBANK_ACTVPTPL",
    #"BANKINTER_BKBKPTPL",
    #"BANCOCTT_CTTVPTPL",
    "CAIXA_GERAL_DEPOSITOS_CGDIPTPL"
]

agreements_requests = []

for bank in SELECTED_BANKS:

    agreements_requests.append(requests.post(
        "https://bankaccountdata.gocardless.com/api/v2/agreements/enduser/",
        headers={
            'accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {response_parsed["access"]}'
        },
        data=json.dumps(
            { "institution_id": bank, 
              "max_historical_days": "90", 
              "access_valid_for_days": "90", 
              "access_scope": ["balances","details","transactions"]
            }
        )
    ))

#%%
agreements_requests_parsed = list(map(lambda x: json.loads(x.content), agreements_requests))
#%%
import webbrowser
from random import random
# Step 4: Build a Link
link_responses = []
min_reference = 12090909
max_reference = 30928792098

for i in range(0,len(SELECTED_BANKS)):
    reference = int(min_reference + (random() * (max_reference - min_reference)))
    curr_response = requests.post(
        "https://bankaccountdata.gocardless.com/api/v2/requisitions/",
        data=json.dumps(
            { "redirect": "http://www.google.com", 
              "institution_id": SELECTED_BANKS[i], 
              "reference": str(reference), 
              "agreement": agreements_requests_parsed[i]["id"],
              "user_language":"EN" 
            }
        ),
        headers={
            'accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {response_parsed["access"]}'
        }
    )
    curr_response_parsed = json.loads(curr_response.content)
    webbrowser.open(curr_response_parsed["link"], new=2)
    link_responses.append(curr_response_parsed)

#%%
input("Press Enter to continue...")

# %%
# List accounts
list_account_responses = []
print("REQUISITIONS\n\n")
for i in range(0, len(SELECTED_BANKS)):
    print(f"{SELECTED_BANKS[i]}: {link_responses[i]['id']}")
    list_account_responses.append(
        requests.get(
            f"https://bankaccountdata.gocardless.com/api/v2/requisitions/{link_responses[i]['id']}/",
            headers={
                'accept': 'application/json',
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {response_parsed["access"]}'
            }
        )
    )

list_account_responses_parsed = [json.loads(x.content) for x in list_account_responses]

#%%
print("\nACCOUNTS:\n")
for i in range(0, len(SELECTED_BANKS)):
    for account in list_account_responses_parsed[i]['accounts']:
        print(f"{SELECTED_BANKS[i]}: {account}")
        print(f"Example of trx:")
        trx_in_account = requests.get(f"https://bankaccountdata.gocardless.com/api/v2/accounts/{account}/transactions/",
                headers={
                    'accept': 'application/json',
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {response_parsed["access"]}'
                })
        print(json.loads(trx_in_account.content)["transactions"]["booked"][0:4])
        print("\n")

# %%
