# Financial Review App

Streamlit + yfinance app for reviewing company financials (ratios, statements, trends, simple DCF, two-company comparison).

## Run
    docker compose up --build
Then open http://localhost:8501

Or without compose:
    docker build -t financial-review .
    docker run -p 8501:8501 financial-review

## Ideas to extend (good M&A practice)
- Accretion/dilution calculator using both companies' EPS and share counts
- Precedent-transaction multiples table loaded from a CSV
- Synergy scenarios feeding into the DCF
