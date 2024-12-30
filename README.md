# IQ Reseller to eBay Integration Tool  

This Python-based automation tool integrates the IQ Reseller ERP system with eBay's API to streamline inventory management and automate product listing processes. The program minimizes manual effort and ensures accurate, up-to-date inventory data on eBay.  

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

## Installation  
1. Clone the repository:  
   ```bash
   git clone https://github.com/yourusername/iq-reseller-ebay-integration.git
   cd iq-reseller-ebay-integration
   ```  
2. Install the required libraries:  
   ```bash
   pip install -r requirements.txt
   ```  

## Usage  
1. Configure your API credentials in the `config.py` file:  
   ```python
   EBAY_API_KEY = "your-ebay-api-key"
   IQ_RESELLER_API_KEY = "your-iq-reseller-api-key"
   ```  
2. Run the program:  
   ```bash
   python main.py
   ```  

## How It Works  
1. **Data Retrieval**: Pulls inventory data from the IQ Reseller ERP system.  
2. **Data Processing**: Cleans and transforms the data to align with eBay's listing requirements.  
3. **Product Listings**: Automates the creation and upload of new listings to eBay.  
4. **Inventory Updates**: Tracks changes in inventory and sends update alerts.  

## Contributing  
Contributions are welcome! Please open an issue or submit a pull request for any suggestions or improvements.  

## Contact  
For questions or support, contact [your email].  
