# 🛒 E-commerce Assistant

An intelligent **E-commerce Assistant Chrome Extension** that helps users track products, monitor prices, view product information, and receive email alerts when the price of a tracked product drops.

The project is designed to make online shopping easier by automatically monitoring products from e-commerce websites and notifying users about important price changes.

---

## 🚀 Features

### 🔍 Product Search & Tracking

* Search for products through the assistant.
* Track a specific product from supported e-commerce websites.
* Store tracked product information for future monitoring.
* Continue monitoring a product even after the user leaves the product page.

### 📦 Product Details

The assistant can collect and display information such as:

* Product name
* Product price
* Product description
* Product image
* Product URL
* Availability
* Product specifications
* Website/store name

### 💰 Price Monitoring

The system continuously monitors the prices of tracked products.

When a product's price changes, the system updates the stored price information.

Example:

```text
Original Price: $500
Current Price: $450

Price Drop: $50
```

### 🔔 Price Drop Alerts

When the price of a tracked product falls, the system automatically sends an email notification to the user.

Example:

```text
🔔 Price Drop Alert!

Product: Samsung Galaxy Smartphone
Previous Price: $450
New Price: $399

You can now check the product at:
[Product Link]
```

### 📧 Email Notifications

Users can provide their email address and receive notifications when:

* A tracked product becomes cheaper.
* A significant price drop occurs.
* Other configured price-monitoring conditions are met.

### 🤖 AI Shopping Assistant

The assistant provides a conversational interface through which users can interact with the system.

For example:

```text
User:
Track this laptop for me.

Assistant:
Sure. I will monitor the product and notify you
when its price drops.
```

Another example:

```text
User:
Show me the details of this product.

Assistant:
Product: Lenovo ThinkPad
Price: $799
RAM: 16GB
Storage: 512GB SSD
Availability: In Stock
```

---

# 🏗️ Project Architecture

The project consists of several main components:

```text
                 ┌──────────────────────┐
                 │     User / Browser   │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │ Chrome Extension     │
                 │   User Interface     │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │ E-commerce Assistant │
                 │      Backend         │
                 └──────────┬───────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
              ▼             ▼             ▼
        ┌──────────┐  ┌──────────┐  ┌────────────┐
        │ Product  │  │ Tracking │  │ AI / Logic │
        │ Scraper  │  │ System   │  │            │
        └──────────┘  └──────────┘  └────────────┘
              │             │
              └─────────────┤
                            ▼
                    ┌──────────────┐
                    │   Database   │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Price Monitor │
                    └──────┬───────┘
                           │
                    Price Changed?
                           │
                    ┌──────┴──────┐
                    │             │
                   NO            YES
                    │             │
                    │             ▼
                    │       ┌────────────┐
                    │       │   Email    │
                    │       │ Notification│
                    │       └────────────┘
                    │
                    ▼
                  Continue
                 Monitoring
```

---

# 🧰 Technologies Used

The exact technologies can be changed depending on the implementation, but the project can be built using the following stack:

### Frontend / Chrome Extension

* HTML5
* CSS3
* JavaScript
* Chrome Extension APIs
* Chrome Manifest V3

### Backend

* Python
* Flask

### Database

Possible database options:

* SQLite
* MySQL
* PostgreSQL
* MongoDB

### Web Scraping / Product Data

Possible tools include:

* Requests
* BeautifulSoup
* Selenium
* Playwright

### AI Assistant

The assistant can optionally use an LLM/API for natural-language interaction.

The AI layer can be used for:

* Understanding user requests
* Extracting product requirements
* Understanding tracking commands
* Generating natural-language responses

### Email

Possible email services include:

* SMTP
* Gmail SMTP
* SendGrid
* Mailgun
* Other transactional email services

---

# 📁 Suggested Project Structure

```text
ecommerce-assistant/
│
├── chrome-extension/
│   │
│   ├── manifest.json
│   ├── popup.html
│   ├── popup.css
│   ├── popup.js
│   ├── content.js
│   ├── background.js
│   └── icons/
│
├── backend/
│   │
│   ├── app.py
│   ├── scraper.py
│   ├── tracker.py
│   ├── database.py
│   ├── email_service.py
│   └── requirements.txt
│
├── database/
│   └── ecommerce.db
│
├── .env
├── .gitignore
└── README.md
```

---

# ⚙️ How the System Works

## 1. User Opens the Extension

The user installs the E-commerce Assistant Chrome Extension and opens it while browsing an e-commerce website.

---

## 2. User Selects a Product

The assistant identifies the product currently being viewed.

For example:

```text
Product:
HP Pavilion Laptop

Price:
$799

Website:
Example Store
```

---

## 3. User Tracks the Product

The user can ask:

```text
Track this product.
```

The assistant stores the product information and tracking details.

Example:

```text
Product ID: 1024
Product Name: HP Pavilion Laptop
Current Price: $799
URL: https://example.com/product
User Email: user@example.com
Tracking: Active
```

---

## 4. Price Monitoring

The backend periodically checks the product page.

For example:

```text
Day 1 → $799
Day 2 → $799
Day 3 → $779
Day 4 → $749
```

The system detects the price reduction.

---

## 5. Email Alert

When the price decreases, an email notification is sent to the user.

```text
Previous Price: $799
New Price: $749
Price Drop: $50
```

The email contains a link to the product.

---

# 💬 Example User Interaction

### Track a Product

```text
User:
Track this smartphone.

Assistant:
Samsung Galaxy S25 has been added to your
price tracking list.
```

### Check Product

```text
User:
What is the current price?

Assistant:
The current price of the Samsung Galaxy S25 is $699.
```

### Price Drop

```text
Assistant:
🔔 Price Drop Detected!

Samsung Galaxy S25

Previous Price: $699
Current Price: $649

You saved $50 compared with the previous price.
```

---

# 🗃️ Database Design

A simple product tracking table can contain:

| Field             | Description           |
| ----------------- | --------------------- |
| `id`              | Unique product ID     |
| `user_email`      | User's email          |
| `product_name`    | Name of product       |
| `product_url`     | Product page URL      |
| `website`         | E-commerce website    |
| `current_price`   | Latest known price    |
| `previous_price`  | Previous price        |
| `currency`        | Product currency      |
| `image_url`       | Product image         |
| `availability`    | Stock status          |
| `tracking_status` | Active/Inactive       |
| `last_checked`    | Last price-check time |
| `created_at`      | Tracking start date   |

---

# 🔄 Price Tracking Workflow

```text
Product Added
      │
      ▼
Store Product Information
      │
      ▼
Check Product Price
      │
      ▼
Compare With Previous Price
      │
      ├───────────────┐
      │               │
      ▼               ▼
Price Same       Price Lower
      │               │
      ▼               ▼
Update Check     Update Price
Time                  │
                      ▼
                Send Email Alert
                      │
                      ▼
                Continue Tracking
```

---

# 🔐 Environment Variables

Sensitive information should not be stored directly in the source code.

Create a `.env` file:

```env
SECRET_KEY=your_secret_key

DATABASE_URL=your_database_url

EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USERNAME=your_email
EMAIL_PASSWORD=your_email_password

AI_API_KEY=your_api_key
```

> Never upload your `.env` file or API keys to GitHub.

Add it to `.gitignore`:

```gitignore
.env
__pycache__/
*.pyc
*.db
venv/
.venv/
```

---

# 📦 Installation

## 1. Clone the Repository

```bash
git clone https://github.com/yourusername/ecommerce-assistant.git
```

Move into the project directory:

```bash
cd ecommerce-assistant
```

---

## 2. Create a Virtual Environment

Windows:

```bash
python -m venv venv
```

Activate it:

```bash
venv\Scripts\activate
```

---

## 3. Install Dependencies

```bash
pip install -r backend/requirements.txt
```

---

## 4. Configure Environment Variables

Create a `.env` file and add the required API keys, database configuration, and email credentials.

---

## 5. Start the Backend

```bash
python backend/app.py
```

The backend will start on the configured local port.

For example:

```text
http://127.0.0.1:5000
```

---

# 🌐 Installing the Chrome Extension

1. Open Google Chrome.
2. Go to:

```text
chrome://extensions/
```

3. Enable **Developer mode**.
4. Click **Load unpacked**.
5. Select the:

```text
chrome-extension/
```

folder.
6. The E-commerce Assistant extension will appear in Chrome.
7. Pin the extension to the Chrome toolbar.

---

# 🧪 Testing

The project should be tested for:

### Product Detection

* Product name detection
* Product price detection
* Product URL detection
* Product image detection
* Website identification

### Tracking

* Adding a product
* Removing a product
* Viewing tracked products
* Updating tracked products

### Price Monitoring

* Price unchanged
* Price increased
* Price decreased
* Product unavailable
* Product page unavailable

### Notifications

* Email configuration
* Price-drop detection
* Email delivery
* Duplicate notification prevention

---

# ⚠️ Important Considerations

Different e-commerce websites use different page structures and technologies. Therefore, product extraction may need to be customized for each supported website.

The project should also respect:

* Website terms of service
* Robots.txt where applicable
* Rate limits
* Copyright restrictions
* User privacy
* Data protection requirements

The system should avoid making excessive requests to e-commerce websites.

---

# 🔮 Future Improvements

Possible future features include:

* 📊 Price history charts
* 📉 Historical lowest-price detection
* 🔔 Custom price targets
* 📧 Multiple notification methods
* 📱 Mobile application
* 🛍️ Support for more e-commerce websites
* 🔎 Product comparison
* 💱 Automatic currency conversion
* 🤖 Improved AI shopping as
