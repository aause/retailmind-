# 🤖 RetailMind — Multi-Agent Sales Analysis System

A **5-agent AI pipeline** that automatically analyzes retail sales data (coffee shops, FMCG, general retail) through an interactive dashboard.

## 🏗️ Architecture

```
OrchestratorAgent
├── DataLoaderAgent    → Load & validate CSV/Excel files
├── CleaningAgent      → Clean data, detect retail domain
├── AnalysisAgent      → Compute KPIs, trends, product insights
└── InsightAgent       → Generate AI insights via Claude API
```

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- Anthropic API key

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set API key
**Windows (PowerShell):**
```powershell
$env:GROQ_API_KEY = "gsk_..."
```
**Mac/Linux:**
```bash
export GROQ_API_KEY="gsk_..."
```

### 4. Run
```bash
python app.py
```

### 5. Open browser
```
http://127.0.0.1:5000
```

## 📁 Project Structure
```
retail_sales_agents/
├── app.py                    # Flask server + all 5 agents
├── requirements.txt
├── sample_coffee_shop.csv    # Sample data to test with
├── uploads/                  # Uploaded files stored here (auto-created)
└── static/
    └── index.html            # Dashboard UI
```

## 📊 Supported Data Formats
- **CSV** (.csv)
- **Excel** (.xlsx, .xls)

### Column Detection (automatic)
| Type | Detected columns |
|------|-----------------|
| Sales | sales, revenue, amount, total, price |
| Quantity | qty, quantity, units, count |
| Product | product, item, name, sku, category |
| Date | date, time, day, month, year |

## 🎯 Domain Detection
The **CleaningAgent** auto-detects your retail domain:
- ☕ **Coffee** — espresso, latte, cafe keywords
- 🛒 **FMCG** — sku, grocery, packaged goods
- 🏪 **Retail** — general retail

## 💡 Tips
- Use the included `sample_coffee_shop.csv` to test
- All columns are detected automatically — no config needed
- Re-run analysis as many times as you like after upload
