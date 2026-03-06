# Virtual Memory Manager

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://samarthjoshi01-virtual-memory-manager-realtime.streamlit.app/)

A **real-time Virtual Memory Manager visualizer** built with Python and Streamlit.  
Simulate page allocation, FIFO / LRU replacement policies, and watch memory frames, hit/fault ratios, and the page table update live.

---

## 🚀 Live Demo

👉 **[Open the live app on Streamlit Cloud](https://samarthjoshi01-virtual-memory-manager-realtime.streamlit.app/)**

---

## ✨ Features

- 🧠 **Real-time memory frame visualization** — colour-coded cards per process
- ⚡ **FIFO & LRU** page-replacement policies, switchable at runtime
- 📊 **Frame occupancy bar chart** with per-PID colouring
- 🥧 **Hit / Fault pie chart** with percentage breakdown
- 📈 **Cumulative hits & faults timeline** — see trends over time
- 📋 **Live activity log** — colour-coded HIT / FAULT / REMOVE events
- 🗂️ **Page table view** — current in-memory pages per process
- 🔄 **Replacement queue** — see which page will be evicted next
- 🤖 **Auto-simulation** mode with configurable interval
- 🖱️ **Manual page access & removal** controls

---

## 🛠️ Local Setup

### Prerequisites

- Python 3.8+

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run the app

```bash
streamlit run realtime.py
```

The app will open at `http://localhost:8501` in your browser.

---

## 📦 Project Structure

```
Virtual_Memory_Manager/
├── realtime.py          # Main Streamlit app
├── requirements.txt     # Python dependencies
├── .streamlit/
│   └── config.toml      # Streamlit theme & server config
└── README.md
```

---

## 🌐 Deploying to Streamlit Community Cloud

1. Push this repository to GitHub (or fork it).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **"New app"**, select this repository, branch `main`, and set `realtime.py` as the main file.
4. Click **Deploy** — your app will be live in seconds!
