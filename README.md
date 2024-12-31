# IQ Reseller to eBay Integration Tool  

This Python-based automation tool integrates the IQ Reseller ERP system with eBay's API to streamline inventory management and automate product listing processes. The program minimizes manual effort and ensures accurate, up-to-date inventory data on eBay.  

The program is set to run each week. The first file 'week0_initialsetup.py' is ran in the first week, and creates the initial datasets that are required for the program to run efficiently. Then the 'weekly_task.py' file is run every week after that.

## Features  
- **Data Synchronization**: Retrieves weekly updates from the IQ Reseller ERP system.  
- **Automated Listings**: Creates and uploads new product listings to eBay.
- **Inventory Updates**: Item quantity update alerts for products with active eBay listings that have new inventory in stock.  
- **Data Cleaning and Transformation**: Formats data to meet eBay’s API requirements, removing inconsistencies and ensuring compliance.  
- **Cost Efficiency**: Reduces manual work by automating repetitive tasks.  

## Prerequisites  
- Python 3.8+  
- `requests` library for API calls  
- eBay developer account and API credentials  
- IQ Reseller ERP system access  

## How It Works  
1. **Data Retrieval**: Pulls inventory data from the IQ Reseller ERP system.  
2. **Data Processing**: Cleans and transforms the data to align with eBay's listing requirements.  
3. **Product Listings**: Automates the creation and upload of new listings to eBay.  
4. **Inventory Updates**: Tracks changes in inventory and sends update alerts.  
