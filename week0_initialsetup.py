import requests
import json
import base64
import math
from datetime import datetime

# STAGE 1: Collect and clean data from IQ Reseller, then filter the items by those that meet eBay requirements

# collect raw data from iq reseller from a specified date until now
def iqreseller_createdataset():
    # API call to retrieve dataset
    url = "https://api.iqreseller.com/webapi.svc/Inventory/JSON/GetInventories?Page=1&PageSize=20000"
    headers = {
    'iqr-session-token': '# insert token here'
    }
    response = requests.request("GET", url, headers=headers) # GET request for inventory data from IQ Reseller
    raw_data = response.json() # raw data stored in this variable

    iqr_data = {}
    for item in raw_data: 
        date_added = datetime.strptime(item.get('added'), '%m/%d/%Y %I:%M:%S %p')
        start_date = datetime(2024, 12, 1) # this can either be modify or change to: previous week = ...

        if date_added >= start_date:
            sku = (item.get('item', '')[:5] + item.get('condition', '')[:5] + item.get('inventorycomments', '')[:5])

            if sku in iqr_data:
                iqr_data[sku]['quantity'] += item.get('quantity', 0) # update quantity if item already in iqr_data 
                iqr_data[sku]['inventory_id'].append([
                    item.get('inventoryid'), 
                    date_added.strftime('%Y-%m-%d')
                    ])
                
                # for items already in iqr_data, if there are new imageurls add them
                new_image = item.get('imageurl') 
                if new_image != "":
                    current_imageurl = iqr_data[sku]['imageurl']
                    if current_imageurl: 
                        iqr_data[sku]['imageurl'] = f"{current_imageurl}|{new_image}"
                    else:
                        iqr_data[sku]['imageurl'] = new_image
                
                # check if received status and status are different, and if even one of them is "available" and "received" update that so it will pass through the data clean
                receivedstatus = item.get('receivedstatus')
                if receivedstatus != iqr_data[sku]['receivedstatus'] and receivedstatus == "Received":
                    iqr_data[sku]['receivedstatus'] = receivedstatus

                status = item.get('status')
                if status != iqr_data[sku]['status'] and status == "Available":
                    iqr_data[sku]['status'] = status

            else:
                iqr_data[sku] = {
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
        else: 
            continue 
                    
    with open("iqr_dataset.json", "w") as file:
        json.dump(iqr_data, file, indent = 4)

# add the category name for each item to the dataset created above
def iqreseller_categoryAttribute():
    # API call to retrieve category attributes
    url = "https://api.iqreseller.com/webapi.svc/MI/JSON/GetItems?pagesize=20000&page=1"
    payload={}
    headers = {
    'iqr-session-token': '# insert token here'
    }
    response = requests.request("GET", url, headers=headers, data=payload)
    categories_data = response.json()

    with open('iqr_dataset.json', 'r') as file: 
        iqr_dataset = json.load(file)

    # get item ID and corresponding category to match with iqr_dataset
    for item in categories_data:
        itemnumber = str(item.get('itemnumber', '')).rstrip() 
        category = item.get('category')

        for sku, attributes in iqr_dataset.items():
            if attributes.get('itemnumber') == itemnumber:
                attributes["category"] = category

    #update iqr_dataset with new category attributes
    with open('iqr_dataset.json', 'w') as file:
        json.dump(iqr_dataset, file, indent = 4)

# Part 1: clean data for ebay - collect all the items that meet the first stage of ebay requirements (category, price, etc.)
def dataclean_part1():
    with open('iqr_dataset.json', 'r') as file: 
        iqr_data = json.load(file)

    clean_ebaydata = []
    for sku, attributes in iqr_data.items():
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
            warehouse in ["MAIN", "SOLEDAD"]
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
            image_url = image_url[:24] # limit amount of image urls to 24 for ebay requirements

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
            clean_ebaydata.append(item_attributes)  # store items that passed conditions into list

    return clean_ebaydata

# Part 2: from item list of products that meet initial requirements: collect the dimensions from inventory attributes
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

# Part 3: clean dimension formats for filtering in the part 4 of the data clean
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

# Part 4: if all dimension attributes are > 0, add dimensions to the item's attribute fields and then store these items in new list
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


# STAGE 2: Create eBay listings and offers items that met requirements in STAGE 1

# generate ebay access token for API calls
def refreshtoken_to_accesstoken():
    token_url = "https://api.ebay.com/identity/v1/oauth2/token"
    # collect IDs/tokens required from eBay Developer Account
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

# create ebay listings from clean_ebaydata list, and store successfully created listings in a list to create offers
def createlistings(access_token, clean_ebaydata):
    ebay_createdlistings = []

    for item in clean_ebaydata:
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
                    "location" : item.get('warehouse'),
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
                    "location" : item.get('warehouse'),
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
                    "location" : item.get('warehouse'),
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
                    "location" : item.get('warehouse'),
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
                    "location" : item.get('warehouse'),
                    "categoryID" : categoryID,
                    "description" : item.get('description'),
                    "price" : item.get('price')
                    })
            else: 
                print(f"Failed to create listing for item number: {itemnumber}.", "Status Code:", statuscode, "Error Message: ", response.text)

    return ebay_createdlistings

# create offer from ebay_createdlistings list
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
                "fulfillmentPolicyId": "",
                "paymentPolicyId": "",
                "returnPolicyId": ""
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
        
        if 200 <= statuscode < 300:
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

# publish offer from ebay_createdoffers list
def publishoffers(access_token, ebay_offerscreated):
    ebay_publishedOffers = {}

    for item in ebay_offerscreated:
        sku = item.get('sku')
        offerID = item.get('offerID')

        publishofferURL = f"https://api.ebay.com/sell/inventory/v1/offer/{offerID}/publish"
        offerheaders = {
            'Authorization': f"Bearer {access_token}",
            'Content-Type': 'application/json',
            'Accept': 'application/json', 
            'Content-Language': 'en-US'
        }
        response = requests.post(publishofferURL, headers = offerheaders)
        statuscode = response.status_code
        
        if 200 <= statuscode < 300:
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

    with open('ebay_publishedOffers.json', 'w') as file:
        json.dump(ebay_publishedOffers, file, indent = 4)
      

# Deliverable:
def main():
    # STAGE 1:

    # create IQR dataset 
    iqreseller_createdataset()
    iqreseller_categoryAttribute()

    # clean and filter items to meet eBay Requirements
    clean_ebaydata = dataclean_part1()
    item_dimensions = dataclean_part2(clean_ebaydata)
    item_dimensions = dataclean_part3(item_dimensions)
    clean_ebaydata = dataclean_part4(item_dimensions, clean_ebaydata)


    # STAGE 2: 

    # genereate ebay access token to use API
    access_token = refreshtoken_to_accesstoken()

    # create create listings, then offers, then publish offers
    ebay_createdlistings = createlistings(access_token, clean_ebaydata)
    ebay_offerscreated = createoffers(access_token, ebay_createdlistings)
    publishoffers(access_token, ebay_offerscreated)
