import requests
import json
import base64
import math
from datetime import datetime, timedelta
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

# generate ebay access token
def refreshtoken_to_accesstoken():
    token_url = "https://api.ebay.com/identity/v1/oauth2/token"
    # collect IDs/Tokens from eBay Developer Account
    client_id = ""
    client_secret = ""
    refresh_token = ""

    auth_str = f"{client_id}:{client_secret}"
    auth_bytes = auth_str.encode("utf-8")
    auth_base64 = base64.b64encode(auth_bytes).decode("utf-8")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {auth_base64}",
    }

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": "https://api.ebay.com/oauth/api_scope https://api.ebay.com/oauth/api_scope/sell.inventory https://api.ebay.com/oauth/api_scope/sell.account"
    }    

    response = requests.post(token_url, headers=headers, data=data)
    access_token = response.json().get("access_token")
    if response.status_code == 200:
        # print("Access Token:", access_token)
        return access_token
    else: 
        print("Failed to obtain access token:", response.status_code, response.text)
        return None


###
# STAGE 1: collect any items that have sold and find the quantity sold, then collect the inventory IDs for those items sold and store in a list
# then compare to the last known quantity from the current dataset, and if different store in list to update inventory ID's on iqr_data
def finditems_sold(access_token):
    solditems_list = {}
    with open('ebay_publishedOffers.json', 'r') as file:
        publishedOffers_dataset = json.load(file)
    
    for sku in publishedOffers_dataset:
        offerID = publishedOffers_dataset[sku].get('offerID')
        old_quantity = publishedOffers_dataset[sku].get('quantity')

        getOfferURL = f"https://api.ebay.com/sell/inventory/v1/offer/{offerID}"
        offerheaders = {
            'Authorization': f"Bearer {access_token}",
            'Content-Type': 'application/json',
            'Accept': 'application/json', 
            'Content-Language': 'en-US'
        }
        response = requests.get(getOfferURL, headers = offerheaders)

        if response.ok:
            offerdata = response.json()
            available_quantity = offerdata.get('availableQuantity', 0)
            if available_quantity != old_quantity and old_quantity > available_quantity:
                # update the publishedOffers_dataset with new available_quantity
                publishedOffers_dataset[sku]['quantity'] = available_quantity
                
                # collect quantity of items sol
                items_sold = old_quantity - available_quantity
                solditems_list[sku] = {
                    "items_sold" : items_sold
                }
    
    with open('ebay_publishedOffers.json', 'w') as file: 
        json.dump(publishedOffers_dataset, file, indent=4)
                 
    return solditems_list

# get oldest inventoryIDs from iqrdata file, store in file, then delete those entries from iqrdata
def collect_inventoryIDs(solditems_list):
    with open('iqr_dataset.json', 'r') as file: # reference the iqr_dataset to 
        iqr_dataset = json.load(file)

    inventoryID_list = []
    for sku in solditems_list:
        items_sold = solditems_list[sku].get('items_sold')
        if sku in iqr_dataset:
            inventoryIDs = iqr_dataset[sku].get('inventory_id', [])
            sorted_IDs = sorted(inventoryIDs, key = lambda x: x[1])
            inventoryIDs_sold = [inv[0] for inv in sorted_IDs[:items_sold]]
            inventoryID_list.extend(inventoryIDs_sold)

    return inventoryID_list 

# email content for inventoryIDs sold
def emailcontent_InventoryIDs(inventoryID_list):
    if inventoryID_list:
        # first paragraph of email
        EC_inventoryIDlist = "\nBelow are the items that have sold on eBay by their Inventory ID's in the last week.\nDelete these inventory ID's from IQ Reseller to reflect the items that have sold.\n\nInventory ID's to delete on IQ Reseller:\n"
        
        # format inventoryID list
        inventoryID_list = "\n".join(map(str, inventoryID_list)) # format list of inventoryIDs to prepare for email
        EC_inventoryIDlist += inventoryID_list
    else:
        EC_inventoryIDlist = "\nThere were no items sold in the past week that were created from this program. No Inventory ID's to delete.\n"
    return EC_inventoryIDlist


###
# STAGE 2: Collect new added quantities of items that have published offers, and collect their SKU's (for reference on eBay) and their added quantities, and store 

# collect new items from IQReseller and store items with existing offers from publishedOffers dataset
def iqreseller_updatedQuantitylist():
    url = "https://api.iqreseller.com/webapi.svc/Inventory/JSON/GetInventories?Page=1&PageSize=20000"
    headers = {
    'iqr-session-token': '# insert token here'
    }
    response = requests.request("GET", url, headers=headers) # GET request for inventory data from IQ Reseller
    new_data = response.json() # raw data stored in this variable

    # open published offers file, to compare with published items on eBay 
    with open('ebay_publishedOffers.json', 'r') as file:
        publishedOffers_dataset = json.load(file)
    
    previous_week = datetime.now() - timedelta(weeks=1)
    updateditems_list = {} # store item's sku's/offerID's and new quantity to later run through the get/post calls to update quantity

    for item in new_data:
        date_added = datetime.strptime(item.get('added'), '%m/%d/%Y %I:%M:%S %p')
        if date_added >= previous_week:
            sku = (item.get('item', '')[:5] + item.get('condition', '')[:5] + item.get('inventorycomments', '')[:5])
            if sku in publishedOffers_dataset:
                
                # add items to updateditems_list if item is already a published offer 
                if sku in updateditems_list:
                    updateditems_list[sku]['quantity'] += item.get('quantity', 0) # update quantity if item already in updatedoffers list 
                    updateditems_list[sku]['inventory_id'].append([
                        item.get('inventoryid'), 
                        date_added.strftime('%Y-%m-%d')
                        ])
                else:
                    updateditems_list[sku] = {  # list to store all the inventoryids associated with this item's unique key 
                        "offerID" : publishedOffers_dataset[sku].get('offerID'),
                        "quantity_added" : item.get('quantity'),
                        "new_availableQuantity": "", 
                        "date_added" : date_added.strftime('%Y-%m-%d'), # date reference
                        "inventory_id" :[[
                            item.get('inventoryid'), 
                            date_added.strftime('%Y-%m-%d')
                        ]
                    ] 
                }
    return updateditems_list

# get request for each sku with existing offers that was added, if still live, store the quantity added for email and insert new inventoryIDs in the main iqr_dataset
def getOffers(access_token, updateditems_list):
    with open('iqr_dataset.json', 'r') as file:
        iqr_dataset = json.load(file)

    newQuantities = {}
    for sku in updateditems_list:
        offerID = updateditems_list[sku].get('offerID')
        quantity_added = updateditems_list[sku].get('quantity_added', 0)
        new_inventoryIDs = updateditems_list[sku].get('inventory_id', [])

        getOfferURL = f"https://api.ebay.com/sell/inventory/v1/offer/{offerID}"
        offerheaders = {
            'Authorization': f"Bearer {access_token}",
            'Content-Type': 'application/json',
            'Accept': 'application/json', 
            'Content-Language': 'en-US'
        }
        response = requests.get(getOfferURL, headers = offerheaders)

        if response.ok:
            # if an offer still exists, store sku and new quantity added
            newQuantities[sku] = {
                "quantity_added" : quantity_added
            }

            # store new inventoryID's in iqr_dataset
            current_inventoryIDs = iqr_dataset[sku].get('inventory_id', [])
            if current_inventoryIDs:
                updated_inventoryIDs = current_inventoryIDs + new_inventoryIDs
                iqr_dataset[sku]['inventory_id'] = updated_inventoryIDs

    return newQuantities

# format email content for added quantities
def emailcontent_newQuantities(newQuantities):
    if newQuantities:
        EC_addedQuantities = "\nPlease update the current quantities listed on eBay to reflect the additional items added.\nUse the SKU as a reference to find the item in eBay.\n\nHere are items to update on eBay:\n"
        
        for sku in newQuantities:
            quantityAdded = newQuantities[sku].get('quantity-added')
            EC_addedQuantities += f"SKU: {sku}, Quantity to Add: {quantityAdded}\n"
    else:
        EC_addedQuantities = "\nThere are no new item quantities to add to live eBay listings this week.\n"
    return EC_addedQuantities


###
# STAGE 3: Create email and send to team for updates on both IQ Reseller and eBay

# structure and format email body
def create_email(EC_addedQuantities, EC_inventoryIDlist):
    email_content = "Hello team, \n\nBelow are the updates based on items added to IQ Reseller in the past week and items that have sold on eBay.\n"
    email_content += EC_addedQuantities
    email_content += EC_inventoryIDlist
    return email_content

# Function to send email
def send_email(email_content):
    # email credentials:
    EMAIL_SERVER = "smtp.gmail.com"
    PORT = ""
    sender_email = ""
    email_password = ""
    receiver_email = ""

    # Email structure
    msg = EmailMessage()
    msg["Subject"] = "Weekly Updates: IQ Reseller & eBay"
    msg["From"] = formataddr(("Weekly Inventory Updates", sender_email))
    msg["To"] = receiver_email
    # Email body
    msg.set_content(email_content)

    # Send email
    with smtplib.SMTP(EMAIL_SERVER, PORT) as server:
        server.starttls()
        server.login(sender_email, password_email)
        server.send_message(msg)


###
# STAGE 4: collect new items that were added in the past week, and any items that have been updated that now meet the eBay requirements, then format and clean data to prepare for eBay

# look for new items created in the past week that are not in iqr_dataset or publishedOffers_dataset and store them in a list
def iqreseller_newitemslist():
    # open publishedOffers file, to ensure new items aren't here
    with open('ebay_publishedOffers.json', 'r') as file:
        publishedOffers_dataset = json.load(file)

    # open iqr_dataset file, to ensure new items aren't here
    with open('iqr_dataset.json', 'r') as file: 
        iqr_dataset = json.load(file)

    # IQ Reseller API call to get items
    url = "https://api.iqreseller.com/webapi.svc/Inventory/JSON/GetInventories?Page=1&PageSize=20000"
    headers = {
    'iqr-session-token': '# insert token here'
    }
    response = requests.request("GET", url, headers=headers) # GET request for inventory data from IQ Reseller
    new_data = response.json() # raw data stored in this variable

    # how far back you want to look for dates in which items were added  
    previous_week = datetime.now() - timedelta(weeks=1)

    # store item's sku's/offerID's and new quantity to later run through the get/post calls to update quantity
    newitems_list = {}

    for item in new_data:
        date_added = datetime.strptime(item.get('added'), '%m/%d/%Y %I:%M:%S %p')
        if date_added >= previous_week:
            sku = (item.get('item', '')[:5] + item.get('condition', '')[:5] + item.get('inventorycomments', '')[:5])
            
            # only allow items that are not in iqr_dataset or publishedOffers_dataset
            if sku not in publishedOffers_dataset and sku not in iqr_dataset:
                if sku in newitems_list:
                    newitems_list[sku]['quantity'] += item.get('quantity', 0) # update quantity if item already in updatedoffers list 
                    newitems_list[sku]['inventory_id'].append([
                        item.get('inventoryid'), 
                        date_added.strftime('%Y-%m-%d')
                        ])
                    
                    # for items already in the dataset, if there are new imageurls add them
                    new_image = item.get('imageurl') 
                    if new_image != "":
                        current_imageurl = newitems_list[sku]['imageurl']
                        if current_imageurl: 
                            newitems_list[sku]['imageurl'] = f"{current_imageurl}|{new_image}"
                        else:
                            newitems_list[sku]['imageurl'] = new_image

                    # check if received status and status are different, and if even one of them is "available" and "received" update that so it will pass through the data clean
                    receivedstatus = item.get('receivedstatus')
                    if receivedstatus != newitems_list[sku]['receivedstatus'] and receivedstatus == "Received":
                        newitems_list[sku]['receivedstatus'] = receivedstatus

                    status = item.get('status')
                    if status != newitems_list[sku]['status'] and status == "Available":
                        newitems_list[sku]['status'] = status

                else:
                    newitems_list[sku] = {   
                        "itemnumber" : str(item.get('item', '')).rstrip(), # item number
                        "itemname" : str(item.get('itemdesc', '')).rstrip(), # 
                        "mfgr" : str(item.get('mfgr', '')).rstrip(), # brand/manufacturer name
                        "mfgrid" : item.get('mfgrid'), # brand/manufacturer id
                        "condition" : str(item.get('condition', '')).rstrip(),
                        "description" : str(item.get('inventorycomments', '')).rstrip(), # description for special condition items
                        "warehouse" : str(item.get('warehouse', '')).rstrip(), # for filtering out medical/direct buyer items
                        "receivedstatus" : str(item.get('receivestatus', '')).rstrip(), # to determine if item is ready to be sold or not
                        "status" : str(item.get('status', '')).rstrip(), # to be used in to filter out those that are "Reserved"
                        "quantity" : item.get('quantity'),
                        "price" : str(item.get('userdefined3', '')).rstrip(), # sale price
                        "imageurl" : item.get('imageurl'), # 1 required, filter out item if no url exists
                        "date_added" : date_added.strftime('%Y-%m-%d'), # date reference
                        "category" : "", 
                        "length" : "", 
                        "width" : "", 
                        "height" : "", 
                        "weight" : "",
                        "imageurl" : item.get('imageurl'), # 1 required, filter out item if no url exists
                        "inventory_id" :[[   # list to store all the inventoryids associated with this item's unique key
                            item.get('inventoryid'), 
                            date_added.strftime('%Y-%m-%d')
                            ]
                        ]
                    }
    return newitems_list

# look for any items already in iqr_data that have an updated attributes that will allow them to go into ebay (receivedstatus, status, imageURLs, price)
def iqreseller_updateditemslist():
    # retrieve existing iqr_dataset to reference the existing items
    with open('iqr_dataset.json', 'r') as file:
        iqr_dataset = json.load(file)

    # retrieve existing ebay_publishedOffers dataset to ensure you're not updating sku's already published on ebay
    with open('ebay_publishedOffers.json', 'r') as file:
        ebay_publishedOffers = json.load(file)

    # API call to retrieve dataset
    url = "https://api.iqreseller.com/webapi.svc/Inventory/JSON/GetInventories?Page=1&PageSize=20000"
    headers = {
    'iqr-session-token': '# insert token here'
    }
    response = requests.request("GET", url, headers=headers) # GET request for inventory data from IQ Reseller
    raw_data = response.json() # raw IQR data stored in this variable

    initialitem_list = {}
    updateditems_list = {} # store any items that had updated attributes in this dictionary

    previous_week = datetime.now() - timedelta(weeks=1)
    start_date = datetime(2024, 11, 1)

    for item in raw_data:
        date_added = datetime.strptime(item.get('added'), '%m/%d/%Y %I:%M:%S %p')
        # only read items that were added between the start date and before the last week
        if date_added >= start_date and date_added < previous_week:
            sku = (item.get('item', '')[:5] + item.get('condition', '')[:5] + item.get('inventorycomments', '')[:5])
            if sku in initialitem_list:
                initialitem_list[sku]['quantity'] += item.get('quantity', 0) # update quantity if item already in iqr_data 
                initialitem_list[sku]['inventory_id'].append([
                    item.get('inventoryid'), 
                    date_added.strftime('%Y-%m-%d')
                    ])
                
                # for items already in iqr_data, if there are new imageurls add them
                new_image = item.get('imageurl') 
                if new_image != "":
                    current_imageurl = initialitem_list[sku]['imageurl']
                    if current_imageurl: 
                        initialitem_list[sku]['imageurl'] = f"{current_imageurl}|{new_image}"
                    else:
                        initialitem_list[sku]['imageurl'] = new_image
                
                # check if received status and status are different, and if even one of them is "available" and "received" update that so it will pass through the data clean
                receivedstatus = item.get('receivedstatus')
                if receivedstatus != initialitem_list[sku]['receivedstatus'] and receivedstatus == "Received":
                    initialitem_list[sku]['receivedstatus'] = receivedstatus

                status = item.get('status')
                if status != initialitem_list[sku]['status'] and status == "Available":
                    initialitem_list[sku]['status'] = status

            else:
                initialitem_list[sku] = {
                    "itemnumber" : str(item.get('item', '')).rstrip(), # item number
                    "itemname" : str(item.get('itemdesc', '')).rstrip(), # 
                    "mfgr" : str(item.get('mfgr', '')).rstrip(), # brand/manufacturer name
                    "mfgrid" : item.get('mfgrid'), # brand/manufacturer id
                    "condition" : str(item.get('condition', '')).rstrip(),
                    "description" : str(item.get('inventorycomments', '')).rstrip(), # description for special condition items
                    "warehouse" : str(item.get('warehouse', '')).rstrip(), # for filtering out medical/direct buyer items
                    "receivedstatus" : str(item.get('receivestatus', '')).rstrip(), # to determine if item is ready to be sold or not
                    "status" : str(item.get('status', '')).rstrip(), # to be used in to filter out those that are "Reserved"
                    "quantity" : item.get('quantity'),
                    "price" : str(item.get('userdefined3', '')).rstrip(), # sale price
                    "imageurl" : item.get('imageurl'), # 1 required, filter out item if no url exists
                    "date_added" : date_added.strftime('%Y-%m-%d'), # date reference
                    "category" : "", 
                    "length" : "", 
                    "width" : "", 
                    "height" : "", 
                    "weight" : "",
                    "imageurl" : item.get('imageurl'), # 1 required, filter out item if no url exists
                    "inventory_id" :[[   # list to store all the inventoryids associated with this item's unique key
                        item.get('inventoryid'), 
                        date_added.strftime('%Y-%m-%d')
                        ]
                    ]
                }

    for sku, attributes in initialitem_list.items():
        # if the item is in our iqr_dataset but has not been published
        if sku in iqr_dataset and sku not in ebay_publishedOffers:
            # check to see if the following conditions have been updated (receivedstatus, status, imageURLs, price):
            conditions_met = True

            receivedstatus = attributes.get('receivedstatus')
            if not receivedstatus == "Received":
                conditions_met = False
            
            status = attributes.get('status')
            if not status == "Available":
                conditions_met = False

            imageurl = attributes.get('imageurl')
            if not imageurl != "":
                conditions_met = False

            price = attributes.get('price')
            if not (price != "" and price != "0"):
                conditions_met = False
            
            if conditions_met:
                # add item to the main list
                updateditems_list[sku] = attributes

                # update values on iqr_data
                iqr_dataset[sku]['receivedstatus'] = receivedstatus
                iqr_dataset[sku]['status'] = status
                iqr_dataset[sku]['imageurl'] = imageurl
                iqr_dataset[sku]['price'] = price
    
    # udpate iqr_dataset for the values that were changed
    with open('iqr_dataset.json', 'w') as file:
        json.dump(iqr_dataset, file, indent=4)

    return updateditems_list

# combine datasets created for new items and updated items
def newAndupdated_itemslist(newitems_list, updateditems_list):
    # combine the two lists created
    item_list = {**newitems_list, **updateditems_list}

    with open('iqr_dataset.json', 'r') as file:
        iqr_data = json.load(file)

    iqr_datasetNEW = {**iqr_data, **item_list}  # add the new items added in the last week to main iqr_dataset

    with open('iqr_dataset.json', 'w') as file: # load the new dataset onto the iqr_dataset json file
        json.dump(iqr_datasetNEW, file, indent=4) 

    return item_list

# add the category name for each item to the dataset created above
def iqreseller_categoryAttribute(item_list):
    # API call to get categories
    url = "https://api.iqreseller.com/webapi.svc/MI/JSON/GetItems?pagesize=20000&page=1"
    payload={}
    headers = {
    'iqr-session-token': '# insert token here'
    }
    response = requests.request("GET", url, headers=headers, data=payload)
    categories_data = response.json()

    # get item ID and corresponding category to match with iqr_dataset
    for item in categories_data:
        itemnumber = str(item.get('itemnumber', '')).rstrip() 
        category = item.get('category')

        for sku, attributes in item_list.items():
            if attributes.get('itemnumber') == itemnumber:
                attributes["category"] = category
    return item_list

# clean data for ebay - collect all the items that meet the first stage of ebay requirements (category, price, etc.)
def dataclean_part1(item_list):
    clean_ebaydata = []
    for sku, attributes in item_list.items():
        # clean price field and format correctly
        price = attributes.get('price')
        if isinstance(price, str):
            price = price.strip()
            if price:
                try:
                    price = float(price)
                except ValueError:
                    price = 0.0
            else:
                price = 0.0
        elif isinstance(price, (int, float)):
            price = float(price)
        else:
            price = 0.0

        condition = attributes.get('condition')
        category = attributes.get('category')
        description = attributes.get('description')
        warehouse = attributes.get('warehouse')
        image_url = attributes.get('imageurl')
        receivedstatus = attributes.get('receivedstatus')
        status = attributes.get('status')

        # update condition names to meet eBay requirements
        if condition == "USED":
            condition = "USED_EXCELLENT"
        elif condition == "ASIS":
            condition = "USED_EXCELLENT"
        elif condition == "NOB": 
            condition = "NEW_OTHER"
        
        # conditions needed to meet ebay requirements
        if (
            price > 0 and
            image_url and 
            receivedstatus == "Received" and
            status == "Available" and
            category not in ["Lab Equipment", "Medical Equipment", "Surplus Service"] and
            condition not in ["RX", "ITR", "SCRP"] and
            warehouse not in ["RX Only", "SCRAP"]
        ):
            # categoryID from category to meet eBay requirements
            if category == "Appliances":
                categoryID = 20715
            elif category == "Audio":
                categoryID = 3278
            elif category in ["Camera", "Video"]:
                categoryID = 27432
            elif category == "Communication":
                categoryID = 3278
            elif category == "Computer":
                categoryID = 177
            elif category == "Entertainment":
                categoryID = 80053
            elif category == "Industrial Equipment":
                categoryID = 26261
            elif category == "Networking":
                categoryID = 11175
            elif category in ["Office Equipment", "Office Supplies"]:
                categoryID = 159711
            elif category in ["Consumer Electronics", "Other Electronics"]:
                categoryID = 61395
            elif category == "Testing Equipment":
                categoryID = 40004
            else: 
                categoryID = 88433

            image_url = image_url.split('|') # clean imageurl formatting in multiple url cases
            image_url = image_url[:24] # limit amount of image urls to 24

            description = description.replace("\n", ". ") # clean inventory comments
            title = f"{attributes.get('itemname')} - {condition[:1]} - {description[:1]}" # create a unique listing title for the item
            title = title[:80]

            item_attributes = {
                "sku" : sku,
                "itemnumber" : attributes.get('itemnumber'),
                "itemname" : attributes.get('itemname'),
                "title" : title,
                "brand" : attributes.get('mfgr'), 
                "brand_id" : attributes.get('mfgrid'), 
                "condition" : condition, 
                "category" : category,
                "categoryID" : categoryID, # converting to string when creating offer 
                "description" : description, 
                "warehouse" : warehouse, 
                "receivedstatus" : receivedstatus,
                "status" : status,
                "quantity" : attributes.get('quantity'), 
                "price" : f"{price:.2f}",  # formating price with 2 decimals for successful ebay upload, and converting to string
                "date" : attributes.get('date_added'),
                "Length" : "", 
                "Width" : "", 
                "Height" : "", 
                "Weight" : "",
                "imageURL" : image_url,
                "inventoryIDs" : attributes.get('inventory_id')
            }
            clean_ebaydata.append(item_attributes)

    return clean_ebaydata

# from item list of products that meet initial requirements: collect the dimensions from inventory attributes
def dataclean_part2(clean_ebaydata):
    item_dimensions = []
    for item in clean_ebaydata:
        sku = item.get('sku')
        inventoryID_list = item.get('inventoryIDs') # collect list of inventoryIDs for each item
        sorted_inventoryIDs = sorted(inventoryID_list, key = lambda x: x[1], reverse = True)
        inventoryid = sorted_inventoryIDs[0][0]

        # api call to collect attributes
        url = f"https://api.iqreseller.com/webapi.svc/InventoryComments/InventoryAttributes/JSON?inventoryid={inventoryid}"
        payload={}
        headers = {
        'iqr-session-token': '# insert token here'
        }
        response = requests.request("GET", url, headers=headers, data=payload)
        response = response.json()

        product = response[0].get('product') if 'product' in response[0] else None # look for the existince of the product field where attributes are stored 
        product_attributes = product.get('attributes') if product else None # collect attributes from product field if they exist
        
        # look for desired attributes in product attribute list if the list exists
        if isinstance(product_attributes, list): # if product attribute list exists
            dimensions = { 
                    "sku" : sku,
                    "Length" : "",
                    "Width" : "", 
                    "Height" : "", 
                    "Weight" : ""
                }
            for attribute in product_attributes: # look through each attribute
                attribute_name = str(attribute.get('name')).rstrip() # format the attribute name to remove whitespace
                attribute_value = attribute.get('value') # format the attribute's value
                
                # first look to see if dimension values have been added to attributes, and if so add the values to the dimensions dictionary
                if attribute_name == "Length":
                    dimensions['Length'] = attribute_value
                if attribute_name == "Width": 
                    dimensions['Width'] = attribute_value
                if attribute_name == "Height":
                    dimensions['Height'] = attribute_value
                if attribute_name == "Weight":
                    dimensions['Weight'] = attribute_value
            
            if dimensions['Length'] == "":
                dimensions['Length'] = "0"
            if dimensions['Width'] == "":
                dimensions['Width'] = "0"
            if dimensions['Height'] == "":
                dimensions['Height'] = "0"
            if dimensions['Weight'] == "":
                dimensions['Weight'] = "0"
            
            item_dimensions.append(dimensions)

    return item_dimensions

# clean dimension formats for filtering in the part 4 of the data clean
def dataclean_part3(item_dimensions):
    # convert each dimension value to appropriate float format for ebay
    for item in item_dimensions:
        # clean Length attribute
        Length = item.get('Length')
        if isinstance(Length, str):
            Length = Length.strip()
            if Length:
                try:
                    Length = float(Length)
                except ValueError:
                    Length = 0.0
            else:
                Length = 0.0
        elif isinstance(Length, (int, float)):
            Length = float(Length)
        else:
            Length = 0.0
        item['Length'] = Length

        # clean Width attribute
        Width = item.get('Width')
        if isinstance(Width, str):
            Width = Width.strip()
            if Width:
                try:
                    Width = float(Width)
                except ValueError:
                    Width = 0.0
            else:
                Width = 0.0
        elif isinstance(Width, (int, float)):
            Width = float(Width)
        else:
            Width = 0.0
        item['Width'] = Width

        # clean Height attribute
        Height = item.get('Height')
        if isinstance(Height, str):
            Height = Height.strip()
            if Height:
                try:
                    Height = float(Height)
                except ValueError:
                    Height = 0.0
            else:
                Height = 0.0
        elif isinstance(Height, (int, float)):
            Height = float(Height)
        else:
            Height = 0.0
        item['Height'] = Height

        # clean Weight attribute
        Weight = item.get('Weight')
        if isinstance(Weight, str):
            Weight = Weight.strip()
            if Weight:
                try:
                    Weight = float(Weight)
                except ValueError:
                    Weight = 0.0
            else:
                Weight = 0.0
        elif isinstance(Weight, (int, float)):
            Weight = float(Weight)
        else:
            Weight = 0.0
        Weight = math.ceil(Weight)
        item['Weight'] = Weight

    return item_dimensions

# if all dimension attributes are > 0, add dimensions to the item's attribute fields and then store these items in new list
def dataclean_part4(item_dimensions, clean_ebaydata):    
    ebay_listingdata = []
    for dimensions in item_dimensions:
        sku_dimensions = dimensions.get('sku')
        Length = dimensions.get('Length')
        Width = dimensions.get('Width')
        Height = dimensions.get('Height')
        Weight = dimensions.get('Weight')
        # if all values are greater than 0 for all dimensions, add dimensions to the item attributes 
        if all(value > 0 for value in [Length, Width, Height, Weight]):
            for item in clean_ebaydata:
                sku = item.get('sku')
                if sku_dimensions == sku:
                    item['Length'] = Length
                    item['Width'] = Width
                    item['Height'] = Height
                    item['Weight'] = Weight
                    ebay_listingdata.append(item)

    return ebay_listingdata

# create eBay listings
def createlistings(access_token, ebay_listingdata):
    ebay_createdlistings = []

    for item in ebay_listingdata:
        categoryID = item.get('categoryID')

        # listings with no aspects required
        if categoryID in [20715, 3278, 26261, 159711, 88433]: 
            # API Call: Create Listing
            sku = item.get('sku')
            itemnumber = item.get('itemnumber')
            createlistingURL = f"https://api.ebay.com/sell/inventory/v1/inventory_item/{sku}"
            listingheaders = {
                'Authorization': f"Bearer {access_token}",
                'Content-Type': 'application/json',
                'Accept': 'application/json', 
                'Content-Language': 'en-US'
            }
            data = {
                "availability": {
                    "shipToLocationAvailability": {
                        "quantity": item.get('quantity')
                    }
                },
                "condition": item.get('condition'),
                "conditionDescription": item.get('description'),
                "packageWeightAndSize" : { 
                    "dimensions" : {
                        "height" : item.get('Height'),
                        "length" : item.get('Length'),
                        "unit" : "INCH", # ask what units to use
                        "width" : item.get('Width')
                    },
                    "weight" : {
                        "unit" : "POUND", # ask what units to use
                        "value" : item.get('Weight')
                    }
                },
                "product": {
                    "aspects": {
                    },
                    "brand": item.get('brand'),
                    "mpn": itemnumber,
                    "description": item.get('description'),
                    "imageUrls": item.get('imageURL'),
                    "title": item.get('title')
                }
            }
            response = requests.put(createlistingURL, headers = listingheaders, json = data)
            statuscode = response.status_code

            # if successful, add item info to createdlistings list, otherwise, print the error message
            if 200 <= statuscode < 300:
                ebay_createdlistings.append({
                    "sku" : sku,
                    "title" : item.get('title'),
                    "quantity" : item.get('quantity'),
                    "categoryID" : categoryID,
                    "description" : item.get('description'),
                    "price" : item.get('price')
                    })
            else: 
                print(f"Failed to create listing for item number: {itemnumber}.", "Status Code:", statuscode, "Error Message: ", response.text)

        # listings with Brand and MPN aspects required
        elif categoryID in [11175, 61395, 40004]: 
            # API Call: Create Listing
            sku = item.get('sku')
            itemnumber = item.get('itemnumber')
            createlistingURL = f"https://api.ebay.com/sell/inventory/v1/inventory_item/{sku}"
            listingheaders = {
                'Authorization': f"Bearer {access_token}",
                'Content-Type': 'application/json',
                'Accept': 'application/json', 
                'Content-Language': 'en-US'
            }
            data = {
                "availability": {
                    "shipToLocationAvailability": {
                        "quantity": item.get('quantity')
                    }
                },
                "condition": item.get('condition'),
                "conditionDescription": item.get('description'),
                "packageWeightAndSize" : { 
                    "dimensions" : {
                        "height" : item.get('Height'),
                        "length" : item.get('Length'),
                        "unit" : "INCH", # ask what units to use
                        "width" : item.get('Width')
                    },
                    "weight" : {
                        "unit" : "POUND", # ask what units to use
                        "value" : item.get('Weight')
                    }
                },
                "product": {
                    "aspects": {
                        "Brand" : [item.get('brand')],
                        "MPN" : [itemnumber]
                    },
                    "brand": item.get('brand'),
                    "mpn": itemnumber,
                    "description": item.get('description'),
                    "imageUrls": item.get('imageURL'),
                    "title": item.get('title')
                }
            }
            response = requests.put(createlistingURL, headers = listingheaders, json = data)
            statuscode = response.status_code

            # if successful, add item info to createdlistings list, otherwise, print the error message
            if 200 <= statuscode < 300:
                ebay_createdlistings.append({
                    "sku" : sku,
                    "title" : item.get('title'),                  
                    "quantity" : item.get('quantity'),
                    "categoryID" : categoryID,
                    "description" : item.get('description'),
                    "price" : item.get('price')
                    })
            else: 
                print(f"Failed to create listing for item number: {itemnumber}.", "Status Code:", statuscode, "Error Message: ", response.text)

        # listings with Brand and Type aspects required
        elif categoryID == 27432:
            # API Call: Create Listing
            sku = item.get('sku')
            itemnumber = item.get('itemnumber')
            createlistingURL = f"https://api.ebay.com/sell/inventory/v1/inventory_item/{sku}"
            listingheaders = {
                'Authorization': f"Bearer {access_token}",
                'Content-Type': 'application/json',
                'Accept': 'application/json', 
                'Content-Language': 'en-US'
            }
            data = {
                "availability": {
                    "shipToLocationAvailability": {
                        "quantity": item.get('quantity')
                    }
                },
                "condition": item.get('condition'),
                "conditionDescription": item.get('description'),
                "packageWeightAndSize" : { 
                    "dimensions" : {
                        "height" : item.get('Height'),
                        "length" : item.get('Length'),
                        "unit" : "INCH", # ask what units to use
                        "width" : item.get('Width')
                    },
                    "weight" : {
                        "unit" : "POUND", # ask what units to use
                        "value" : item.get('Weight')
                    }
                },
                "product": {
                    "aspects": {
                        "Brand" : [item.get('brand')],
                        "Type" : ["Unknown"]
                    },
                    "brand": item.get('brand'),
                    "mpn": itemnumber,
                    "description": item.get('description'),
                    "imageUrls": item.get('imageURL'),
                    "title": item.get('title')
                }
            }
            response = requests.put(createlistingURL, headers = listingheaders, json = data)
            statuscode = response.status_code

            # if successful, add item info to createdlistings list, otherwise, print the error message
            if 200 <= statuscode < 300:
                ebay_createdlistings.append({
                    "sku" : sku,
                    "title" : item.get('title'),                  
                    "quantity" : item.get('quantity'),
                    "categoryID" : categoryID,
                    "description" : item.get('description'),
                    "price" : item.get('price')
                    })
            else: 
                print(f"Failed to create listing for item number: {itemnumber}.", "Status Code:", statuscode, "Error Message: ", response.text)

        # listings with Brand and Screen Size aspects required
        elif categoryID == 80053:
            # API Call: Create Listing
            sku = item.get('sku')
            itemnumber = item.get('itemnumber')
            createlistingURL = f"https://api.ebay.com/sell/inventory/v1/inventory_item/{sku}"
            listingheaders = {
                'Authorization': f"Bearer {access_token}",
                'Content-Type': 'application/json',
                'Accept': 'application/json', 
                'Content-Language': 'en-US'
            }
            data = {
                "availability": {
                    "shipToLocationAvailability": {
                        "quantity": item.get('quantity')
                    }
                },
                "condition": item.get('condition'),
                "conditionDescription": item.get('description'),
                "packageWeightAndSize" : { 
                    "dimensions" : {
                        "height" : item.get('Height'),
                        "length" : item.get('Length'),
                        "unit" : "INCH", # ask what units to use
                        "width" : item.get('Width')
                    },
                    "weight" : {
                        "unit" : "POUND", # ask what units to use
                        "value" : item.get('Weight')
                    }
                },
                "product": {
                    "aspects": {
                        "Brand" : [item.get('brand')],
                        "Screen Size" : ["Unknown"]
                    },
                    "brand": item.get('brand'),
                    "mpn": itemnumber,
                    "description": item.get('description'),
                    "imageUrls": item.get('imageURL'),
                    "title": item.get('title')
                }
            }
            response = requests.put(createlistingURL, headers = listingheaders, json = data)
            statuscode = response.status_code

            # if successful, add item info to createdlistings list, otherwise, print the error message
            if 200 <= statuscode < 300:
                ebay_createdlistings.append({
                    "sku" : sku,
                    "title" : item.get('title'),
                    "quantity" : item.get('quantity'),
                    "categoryID" : categoryID,
                    "description" : item.get('description'),
                    "price" : item.get('price')
                    })
            else: 
                print(f"Failed to create listing for item number: {itemnumber}.", "Status Code:", statuscode, "Error Message: ", response.text)

        # listings with Brand, Screen Size, and Processor aspects required
        elif categoryID == 177:
            # API Call: Create Listing
            sku = item.get('sku')
            itemnumber = item.get('itemnumber')
            createlistingURL = f"https://api.ebay.com/sell/inventory/v1/inventory_item/{sku}"
            listingheaders = {
                'Authorization': f"Bearer {access_token}",
                'Content-Type': 'application/json',
                'Accept': 'application/json', 
                'Content-Language': 'en-US'
            }
            data = {
                "availability": {
                    "shipToLocationAvailability": {
                        "quantity": item.get('quantity')
                    }
                },
                "condition": item.get('condition'),
                "conditionDescription": item.get('description'),
                "packageWeightAndSize" : { 
                    "dimensions" : {
                        "height" : item.get('Height'),
                        "length" : item.get('Length'),
                        "unit" : "INCH", # ask what units to use
                        "width" : item.get('Width')
                    },
                    "weight" : {
                        "unit" : "POUND", # ask what units to use
                        "value" : item.get('Weight')
                    }
                },
                "product": {
                    "aspects": {
                        "Brand" : [item.get('brand')],
                        "Screen Size" : ["Unknown"],
                        "Processor" : ["Unknown"]
                    },
                    "brand": item.get('brand'),
                    "mpn": itemnumber,
                    "description": item.get('description'),
                    "imageUrls": item.get('imageURL'),
                    "title": item.get('title')
                }
            }
            response = requests.put(createlistingURL, headers = listingheaders, json = data)
            statuscode = response.status_code

            # if successful, add item info to createdlistings list, otherwise, print the error message
            if 200 <= statuscode < 300:
                ebay_createdlistings.append({
                    "sku" : sku,
                    "title" : item.get('title'),
                    "quantity" : item.get('quantity'),
                    "categoryID" : categoryID,
                    "description" : item.get('description'),
                    "price" : item.get('price')
                    })
            else: 
                print(f"Failed to create listing for item number: {itemnumber}.", "Status Code:", statuscode, "Error Message: ", response.text)

    return ebay_createdlistings

# create eBay offers
def createoffers(access_token, ebay_createdlistings):
    ebay_offerscreated = []
    for item in ebay_createdlistings:
        sku = item.get('sku')
        categoryID = str(item.get('categoryID'))

        # set location based on warehouse name
        location = item.get('location')
        if location == "MAIN":
            merchantLocationkey = "FremontLocation"
        else:
            merchantLocationkey = "SoledadLocation"

        # API call
        createofferURL = "https://api.ebay.com/sell/inventory/v1/offer"
        offerheaders = {
            'Authorization': f"Bearer {access_token}",
            'Content-Type': 'application/json',
            'Accept': 'application/json', 
            'Content-Language': 'en-US'
        }
        data = {
            "sku": sku,
            "marketplaceId": "EBAY_US",
            "merchantLocationKey" : merchantLocationkey, 
            "format": "FIXED_PRICE",
            "availableQuantity": item.get('quantity'),
            "categoryId": categoryID,
            "listingDescription": item.get('description'),
            "listingDuration" : "GTC", 
            "listingPolicies": {
                "fulfillmentPolicyId": "240272382024",
                "paymentPolicyId": "234537548024",
                "returnPolicyId": "234939264024"
            },
            "pricingSummary": {
                "price": {
                    "currency": "USD",
                    "value": item.get('price')
                }
            }
        }
        response = requests.post(createofferURL, headers = offerheaders, json = data)
        statuscode = response.status_code
        offerID = response.json().get("offerId")
        
        if 200 <= statuscode < 300: # if successful, store necessary item attributes in ebay_offerscreated list
            ebay_offerscreated.append({
                "sku" : sku,
                "title" : item.get('title'),
                "offerID" : offerID,
                "quantity" : item.get('quantity'),
                "categoryID": item.get('categoryID'),
                "listingDescription": item.get('description'),
                "price": item.get('price')
            })
        else: 
            print(f"Failed to create offer for item: {item.get('title')}.", "Status Code:", statuscode, "Error Message: ", response.text)
    
    return ebay_offerscreated

# publish offers
def publishoffers(access_token, ebay_offerscreated):
    ebay_publishedOffers = {}
    for item in ebay_offerscreated:
        sku = item.get('sku')
        offerID = item.get('offerID')

        # API call
        publishofferURL = f"https://api.ebay.com/sell/inventory/v1/offer/{offerID}/publish"
        offerheaders = {
            'Authorization': f"Bearer {access_token}",
            'Content-Type': 'application/json',
            'Accept': 'application/json', 
            'Content-Language': 'en-US'
        }
        response = requests.post(publishofferURL, headers = offerheaders)
        statuscode = response.status_code
        
        if 200 <= statuscode < 300: # store published items in the main ebay_publishedOffers
           ebay_publishedOffers[sku] = {
                "title" : item.get('title'),
                "offerID" : offerID,
                "quantity" : item.get('quantity'),
                "categoryID" : item.get('categoryID'),
                "listingDescription" : item.get('listingDescription'),
                "price" : item.get('price'),
                "date_created" : datetime.now().strftime('%Y-%m-%d'), 
                "last_updated" : "",
           }
        else: 
            print(f"Failed to publish offer for item: {item.get('title')}.", "Status Code:", statuscode, "Error Message: ", response.text)

            # also delete the offer, allowing it to be created again once it meets the requirements
            url = f'https://api.ebay.com/sell/inventory/v1/offer/{offerID}'
            headers = {
                'Authorization': f"Bearer {access_token}"
            }
            response = requests.delete(url, headers=headers)
            if response.ok:
                print(f"Item offer was also deleted. Please try again in next week's program run or upload manually.")


    with open('ebay_publishedOffers.json', 'r') as file: # open the publishedOffers file to combine with the new offers 
        publishedOffers_dataset = json.load(file)

    new_publishedOffers_dataset = {**publishedOffers_dataset, **ebay_publishedOffers} # combine the old publishedOffers data with the new published Offers

    with open('ebay_publishedOffers.json', 'w') as file: # update the file with the new offers
        json.dump(new_publishedOffers_dataset, file, indent=4)


# Deliverable:
def main():
    # generate ebay token for API calls
    access_token = refreshtoken_to_accesstoken()


    # STAGE 1:
    # data collection on items sold in the last week
    solditems_list = finditems_sold(access_token)
    inventoryID_list = collect_inventoryIDs(solditems_list)
    EC_inventoryIDlist = emailcontent_InventoryIDs(inventoryID_list)


    # STAGE 2:
    # data collection on items that were added in the last week that have live listings
    updateditems_list = iqreseller_updatedQuantitylist()
    newQuantities = getOffers(access_token, updateditems_list)
    EC_addedQuantities = emailcontent_newQuantities(newQuantities)


    # STAGE 3: 
    # create and send email
    email_content = create_email(EC_addedQuantities, EC_inventoryIDlist)
    send_email(email_content)


    # STAGE 4:
    # data collection
    newitems_list = iqreseller_newitemslist() # collect new items added to IQR in the last week
    updateditems_list = iqreseller_updateditemslist() # collect items from IQR that have updated attributes
    item_list = newAndupdated_itemslist(newitems_list, updateditems_list) # create list that combines the two lists above that will be cleaned and used for ebay
    item_list = iqreseller_categoryAttribute(item_list) # add category attribute to item_list dataset

    # clean dataset to prepare for eBay listing upload
    clean_ebaydata = dataclean_part1(item_list) # intial data clean/formatting
    item_dimensions = dataclean_part2(clean_ebaydata) # get item dimensions
    item_dimensions = dataclean_part3(item_dimensions) # format dimensions
    ebay_listingdata = dataclean_part4(item_dimensions, clean_ebaydata) # create new list with items that have valid dimensions (greater than 0)

    # eBay create listing, offer, and publish offers
    ebay_createdlistings = createlistings(access_token, ebay_listingdata) # create listings, store successfully created listings in list
    ebay_offerscreated = createoffers(access_token, ebay_createdlistings) # create offers, store successfully offers in list
    publishoffers(access_token, ebay_offerscreated) # publish offers and add successful published offers to the publishedOffers dataset
