"""
Multi-Agent Retail Sales Analysis System
=========================================
Agents:
  1. DataLoaderAgent      - Loads & validates uploaded CSV/Excel files
  2. CleaningAgent        - Cleans, normalizes, detects retail type
  3. AnalysisAgent        - Computes KPIs, trends, product insights
  4. InsightAgent         - Generates natural-language insights via Groq API
  5. OrchestratorAgent    - Coordinates all agents and streams results to UI
"""

import os, json, asyncio, traceback
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
import pandas as pd
import numpy as np
from groq import Groq

# Load GROQ_API_KEY from .env file automatically
load_dotenv()

app = Flask(__name__, static_folder="static")
UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# ─────────────────────────── AGENTS ────────────────────────────────────────

class DataLoaderAgent:
    """Agent 1 – Load and basic-validate the file."""
    name = "DataLoaderAgent"

    def run(self, filepath: str) -> dict:
        path = Path(filepath)
        ext = path.suffix.lower()
        try:
            if ext == ".csv":
                df = pd.read_csv(filepath, encoding="utf-8", on_bad_lines="skip")
            elif ext in (".xlsx", ".xls"):
                df = pd.read_excel(filepath)
            else:
                return {"ok": False, "error": f"Unsupported file type: {ext}"}

            if df.empty:
                return {"ok": False, "error": "File is empty."}

            return {
                "ok": True,
                "df": df,
                "rows": len(df),
                "cols": list(df.columns),
                "message": f"Loaded {len(df):,} rows × {len(df.columns)} columns."
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}


class CleaningAgent:
    """Agent 2 – Clean data and detect retail domain."""
    name = "CleaningAgent"

    DOMAIN_KEYWORDS = {
        "coffee": ["coffee", "espresso", "latte", "cappuccino", "brew", "barista", "cafe"],
        "fmcg": ["sku", "fmcg", "grocery", "supermarket", "packaged", "brand", "category"],
        "retail": ["sale", "revenue", "product", "store", "item", "price", "quantity", "customer"],
    }

    def run(self, df: pd.DataFrame) -> dict:
        df = df.copy()
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        # Drop fully empty columns/rows
        df.dropna(how="all", axis=1, inplace=True)
        df.dropna(how="all", axis=0, inplace=True)

        # Detect date columns
        date_cols = []
        for col in df.columns:
            if any(k in col for k in ["date", "time", "day", "month", "year"]):
                try:
                    df[col] = pd.to_datetime(df[col], infer_format=True, errors="coerce")
                    date_cols.append(col)
                except Exception:
                    pass

        # Detect numeric columns
        for col in df.select_dtypes(include="object").columns:
            try:
                df[col] = pd.to_numeric(df[col].str.replace(r"[,$₹£€]", "", regex=True), errors="ignore")
            except Exception:
                pass

        # Detect domain
        col_str = " ".join(df.columns).lower()
        domain = "retail"
        for d, kws in self.DOMAIN_KEYWORDS.items():
            if any(k in col_str for k in kws):
                domain = d
                break

        # Identify key columns heuristically
        sales_col = next((c for c in df.columns if any(k in c for k in ["sales", "revenue", "amount", "total", "price"])), None)
        qty_col   = next((c for c in df.columns if any(k in c for k in ["qty", "quantity", "units", "count"])), None)
        prod_col  = next((c for c in df.columns if any(k in c for k in ["product", "item", "name", "sku", "category", "type"])), None)

        return {
            "ok": True,
            "df": df,
            "domain": domain,
            "date_cols": date_cols,
            "sales_col": sales_col,
            "qty_col": qty_col,
            "prod_col": prod_col,
            "message": f"Data cleaned. Domain detected: {domain.upper()}. Date cols: {date_cols}"
        }


class AnalysisAgent:
    """Agent 3 – Compute KPIs and structured insights."""
    name = "AnalysisAgent"

    def run(self, df: pd.DataFrame, meta: dict) -> dict:
        results = {}
        sales_col = meta.get("sales_col")
        qty_col   = meta.get("qty_col")
        prod_col  = meta.get("prod_col")
        date_cols = meta.get("date_cols", [])

        # ── Revenue / Sales KPIs ──
        if sales_col and sales_col in df.columns:
            s = pd.to_numeric(df[sales_col], errors="coerce").dropna()
            results["total_revenue"]   = round(float(s.sum()), 2)
            results["avg_order_value"] = round(float(s.mean()), 2)
            results["max_sale"]        = round(float(s.max()), 2)
            results["min_sale"]        = round(float(s.min()), 2)
            results["std_dev"]         = round(float(s.std()), 2)

        # ── Quantity KPIs ──
        if qty_col and qty_col in df.columns:
            q = pd.to_numeric(df[qty_col], errors="coerce").dropna()
            results["total_units_sold"] = int(q.sum())
            results["avg_units"]        = round(float(q.mean()), 2)

        # ── Top Products ──
        if prod_col and prod_col in df.columns:
            if sales_col and sales_col in df.columns:
                top = (df.groupby(prod_col)[sales_col]
                         .sum().sort_values(ascending=False)
                         .head(10).round(2))
                results["top_products"] = top.to_dict()
            counts = df[prod_col].value_counts().head(10).to_dict()
            results["product_freq"] = {str(k): int(v) for k, v in counts.items()}

        # ── Time Series ──
        if date_cols and sales_col and sales_col in df.columns:
            dc = date_cols[0]
            tmp = df[[dc, sales_col]].copy()
            tmp[sales_col] = pd.to_numeric(tmp[sales_col], errors="coerce")
            tmp = tmp.dropna()
            tmp["month"] = tmp[dc].dt.to_period("M").astype(str)
            monthly = tmp.groupby("month")[sales_col].sum().round(2)
            results["monthly_sales"] = monthly.to_dict()

        # ── Category breakdown ──
        cat_cols = [c for c in df.columns if any(k in c for k in ["category", "type", "segment", "region", "store"])]
        if cat_cols and sales_col and sales_col in df.columns:
            cat_breakdown = {}
            for cc in cat_cols[:2]:
                gb = df.groupby(cc)[sales_col].sum().sort_values(ascending=False).head(8).round(2)
                cat_breakdown[cc] = gb.to_dict()
            results["category_breakdown"] = cat_breakdown

        # ── Row summary ──
        results["total_records"]   = len(df)
        results["columns_present"] = list(df.columns)

        return {"ok": True, "kpis": results, "message": "KPI analysis complete."}


class InsightAgent:
    """Agent 4 – Use Groq API to generate natural-language insights."""
    name = "InsightAgent"

    SYSTEM_PROMPT = """You are a senior retail business analyst. 
Given structured KPI data from a retail dataset (could be coffee shop, FMCG, or general retail),
provide sharp, actionable insights. Structure your response in these sections:
1. 🏆 Performance Summary (2-3 sentences)
2. 📈 Key Trends (3-4 bullet points)
3. ⚠️ Areas of Concern (2-3 bullet points)
4. 💡 Recommendations (3-4 actionable bullet points)
Be specific with numbers from the data. Keep it concise and professional."""

    def run(self, kpis: dict, domain: str) -> str:
        prompt = f"""Retail Domain: {domain.upper()}

KPI Data:
{json.dumps(kpis, indent=2, default=str)}

Generate business insights for this retail dataset."""

        try:
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=1500,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"⚠️ Insight generation failed: {e}"


class OrchestratorAgent:
    """Agent 5 – Coordinate all agents and stream status updates."""
    name = "OrchestratorAgent"

    def __init__(self):
        self.loader   = DataLoaderAgent()
        self.cleaner  = CleaningAgent()
        self.analyzer = AnalysisAgent()
        self.insight  = InsightAgent()

    def run(self, filepath: str):
        """Generator: yields SSE-formatted JSON events."""

        def event(agent, status, message, data=None):
            payload = {"agent": agent, "status": status, "message": message}
            if data:
                payload["data"] = data
            return f"data: {json.dumps(payload, default=str)}\n\n"

        # ── Agent 1: Load ──
        yield event("DataLoaderAgent", "running", "📂 Loading and validating file…")
        load_res = self.loader.run(filepath)
        if not load_res["ok"]:
            yield event("DataLoaderAgent", "error", load_res["error"])
            return
        yield event("DataLoaderAgent", "done", load_res["message"],
                    {"rows": load_res["rows"], "cols": load_res["cols"]})

        # ── Agent 2: Clean ──
        yield event("CleaningAgent", "running", "🧹 Cleaning data and detecting domain…")
        clean_res = self.cleaner.run(load_res["df"])
        if not clean_res["ok"]:
            yield event("CleaningAgent", "error", "Cleaning failed.")
            return
        yield event("CleaningAgent", "done", clean_res["message"],
                    {"domain": clean_res["domain"],
                     "sales_col": clean_res["sales_col"],
                     "prod_col": clean_res["prod_col"]})

        # ── Agent 3: Analyze ──
        yield event("AnalysisAgent", "running", "📊 Computing KPIs and trends…")
        analysis_res = self.analyzer.run(
            clean_res["df"],
            {k: clean_res[k] for k in ["sales_col", "qty_col", "prod_col", "date_cols"]}
        )
        if not analysis_res["ok"]:
            yield event("AnalysisAgent", "error", "Analysis failed.")
            return
        yield event("AnalysisAgent", "done", analysis_res["message"],
                    {"kpis": analysis_res["kpis"]})

        # ── Agent 4: Insights ──
        yield event("InsightAgent", "running", "🤖 Generating AI insights with Claude…")
        insights = self.insight.run(analysis_res["kpis"], clean_res["domain"])
        yield event("InsightAgent", "done", "AI insights ready.",
                    {"insights": insights})

        # ── Final ──
        yield event("OrchestratorAgent", "complete", "✅ Analysis pipeline complete!",
                    {"domain": clean_res["domain"], "kpis": analysis_res["kpis"]})


# ─────────────────────────── ROUTES ────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "Empty filename"}), 400
    allowed = {".csv", ".xlsx", ".xls"}
    ext = Path(f.filename).suffix.lower()
    if ext not in allowed:
        return jsonify({"error": f"Unsupported format. Use: {', '.join(allowed)}"}), 400
    save_path = UPLOAD_FOLDER / f.filename
    f.save(save_path)
    return jsonify({"ok": True, "filename": f.filename, "path": str(save_path)})

@app.route("/analyze")
def analyze():
    filename = request.args.get("filename")
    if not filename:
        return jsonify({"error": "filename param required"}), 400
    filepath = UPLOAD_FOLDER / filename
    if not filepath.exists():
        return jsonify({"error": "File not found"}), 404

    orchestrator = OrchestratorAgent()

    def generate():
        for chunk in orchestrator.run(str(filepath)):
            yield chunk

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

if __name__ == "__main__":
    print("\n🚀  Retail Multi-Agent Analysis System")
    print("   Open: http://127.0.0.1:5000\n")
    app.run(debug=True, threaded=True, port=5000)
