# realtime.py
# Installation: pip install streamlit streamlit-autorefresh matplotlib pandas
# Run:
#   streamlit run realtime.py


import time
import random
from collections import deque, OrderedDict

# Safe Streamlit imports
try:
    import streamlit as st
    try:
        from streamlit_autorefresh import st_autorefresh
        HAS_AUTORELOAD = True
    except Exception:
        st_autorefresh = None
        HAS_AUTORELOAD = False
    ST_AVAILABLE = True
except Exception:
    ST_AVAILABLE = False

# visualization libs
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend required for Streamlit server environments
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd
import numpy as np

# UI constants
MAX_HISTORY_SIZE = 200   # max data points kept for the hits/faults timeline
MAX_FRAMES_PER_ROW = 8  # max frame cards rendered per row
LOG_DISPLAY_LIMIT = 30  # number of recent log lines shown in the activity log

# PID color palette (for frame cards)
PID_COLORS = ["#6C63FF", "#FF6584", "#43C59E", "#F9A826", "#E74C3C", "#3498DB"]

def pid_color(pid):
    return PID_COLORS[(pid - 1) % len(PID_COLORS)]

# ------------------------- Replacement Strategies -------------------------
class FIFOReplacement:
    def __init__(self):
        self.queue = deque()

    def access_page(self, page):
        # FIFO does not reorder on access
        pass

    def evict_page(self):
        if not self.queue:
            raise IndexError("No pages to evict")
        return self.queue.popleft()

    def add_page(self, page):
        if page not in self.queue:
            self.queue.append(page)

    def remove_page(self, page):
        self.queue = deque(p for p in self.queue if p != page)


class LRUReplacement:
    def __init__(self):
        self.pages = OrderedDict()

    def access_page(self, page):
        if page in self.pages:
            self.pages.move_to_end(page)

    def evict_page(self):
        if not self.pages:
            raise IndexError("No pages to evict")
        page, _ = self.pages.popitem(last=False)
        return page

    def add_page(self, page):
        self.pages[page] = True
        self.pages.move_to_end(page)

    def remove_page(self, page):
        if page in self.pages:
            del self.pages[page]


# ------------------------- Memory Manager -------------------------
class Memory:
    def __init__(self, total_frames=4, policy="FIFO"):
        self.total_frames = total_frames
        self.frames = [None] * total_frames
        self.free_frames = list(range(total_frames))
        self.page_table = {}
        self.page_faults = 0
        self.page_hits = 0
        self.logs = []
        self.history_hits = []
        self.history_faults = []
        self.set_policy(policy)

    def set_policy(self, policy):
        self.policy = policy.upper()
        self.replacement = LRUReplacement() if self.policy == "LRU" else FIFOReplacement()
        self.log(f"Policy set to {self.policy}")

    def log(self, text):
        ts = time.strftime("%H:%M:%S")
        self.logs.append(f"[{ts}] {text}")
        if len(self.logs) > 1000:
            self.logs = self.logs[-1000:]

    def allocate_page(self, pid, page):
        page_tuple = (pid, page)
        if page_tuple in self.frames:
            self.page_hits += 1
            self.replacement.access_page(page_tuple)
            self.log(f"✅ HIT  — PID {pid}, Page {page}")
            self.history_hits.append(self.page_hits)
            self.history_faults.append(self.page_faults)
            return True
        self.page_faults += 1
        self.log(f"⚠️  FAULT — PID {pid}, Page {page}")
        if self.free_frames:
            frame = self.free_frames.pop(0)
            self.frames[frame] = page_tuple
            self.page_table.setdefault(pid, set()).add(page)
            self.replacement.add_page(page_tuple)
            self.log(f"   ↳ Loaded into Frame {frame}")
        else:
            victim = self.replacement.evict_page()
            try:
                victim_frame = self.frames.index(victim)
            except ValueError:
                victim_frame = 0
            old_pid, old_page = victim
            if old_pid in self.page_table and old_page in self.page_table[old_pid]:
                self.page_table[old_pid].remove(old_page)
            self.frames[victim_frame] = page_tuple
            self.page_table.setdefault(pid, set()).add(page)
            self.replacement.add_page(page_tuple)
            self.log(f"   ↳ Evicted PID {old_pid} Page {old_page} → Frame {victim_frame}")
        self.history_hits.append(self.page_hits)
        self.history_faults.append(self.page_faults)
        if len(self.history_hits) > MAX_HISTORY_SIZE:
            self.history_hits = self.history_hits[-MAX_HISTORY_SIZE:]
            self.history_faults = self.history_faults[-MAX_HISTORY_SIZE:]
        return False

    def remove_page(self, pid, page):
        page_tuple = (pid, page)
        if page_tuple in self.frames:
            idx = self.frames.index(page_tuple)
            self.frames[idx] = None
            self.free_frames.append(idx)
            if pid in self.page_table and page in self.page_table[pid]:
                self.page_table[pid].remove(page)
            self.replacement.remove_page(page_tuple)
            self.log(f"🗑️  Removed PID {pid} Page {page} from Frame {idx}")

    def stats(self):
        total = self.page_faults + self.page_hits
        hit_ratio = self.page_hits / total if total else 0
        fault_ratio = self.page_faults / total if total else 0
        return {
            "Page Faults": self.page_faults,
            "Page Hits": self.page_hits,
            "Hit Ratio": round(hit_ratio, 3),
            "Fault Ratio": round(fault_ratio, 3),
            "Total Accesses": total,
        }

# ========================= Streamlit UI =========================
if ST_AVAILABLE:
    st.set_page_config(
        page_title="Virtual Memory Manager",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ---------- Custom CSS ----------
    st.markdown("""
    <style>
    /* ---- Global ---- */
    body, .stApp { background-color: #0E1117; }

    /* ---- Header ---- */
    .vmm-header {
        background: linear-gradient(135deg, #6C63FF 0%, #3A3680 100%);
        border-radius: 14px;
        padding: 22px 30px 18px 30px;
        margin-bottom: 20px;
    }
    .vmm-header h1 { color: #fff; font-size: 2.1rem; margin: 0; }
    .vmm-header p  { color: #d4d0ff; font-size: 0.95rem; margin: 4px 0 0 0; }

    /* ---- Metric cards ---- */
    .metric-card {
        background: #1A1D2E;
        border: 1px solid #2D2F45;
        border-radius: 12px;
        padding: 16px 20px;
        text-align: center;
        margin-bottom: 10px;
    }
    .metric-card .label { color: #9395A5; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; }
    .metric-card .value { color: #FAFAFA; font-size: 2rem; font-weight: 700; margin: 6px 0 0 0; }
    .metric-card .sub   { font-size: 0.82rem; margin-top: 2px; }

    /* ---- Frame cards ---- */
    .frame-card {
        border-radius: 12px;
        padding: 14px 10px;
        text-align: center;
        margin: 4px;
        border: 2px solid transparent;
        transition: transform 0.15s;
    }
    .frame-card:hover { transform: translateY(-2px); }
    .frame-card .frame-id  { font-size: 0.72rem; color: #9395A5; text-transform: uppercase; letter-spacing: 1px; }
    .frame-card .frame-pid { font-size: 1.05rem; font-weight: 700; margin-top: 6px; }
    .frame-card .frame-pg  { font-size: 0.88rem; margin-top: 2px; }

    /* ---- Section headers ---- */
    .section-header {
        font-size: 1.05rem;
        font-weight: 600;
        color: #FAFAFA;
        border-left: 4px solid #6C63FF;
        padding-left: 10px;
        margin: 18px 0 12px 0;
    }

    /* ---- Log lines ---- */
    .log-hit   { color: #43C59E; font-family: monospace; font-size: 0.82rem; }
    .log-fault { color: #F9A826; font-family: monospace; font-size: 0.82rem; }
    .log-info  { color: #9395A5; font-family: monospace; font-size: 0.78rem; }
    .log-remove{ color: #FF6584; font-family: monospace; font-size: 0.82rem; }

    /* ---- Progress bar override ---- */
    .stProgress > div > div { background: #6C63FF !important; }

    /* ---- Sidebar ---- */
    section[data-testid="stSidebar"] { background: #13152A; }
    </style>
    """, unsafe_allow_html=True)

    # ---------- Page header ----------
    st.markdown("""
    <div class="vmm-header">
      <h1>🧠 Virtual Memory Manager</h1>
      <p>Real-time page allocation, replacement &amp; performance visualizer</p>
    </div>
    """, unsafe_allow_html=True)

    # ---------- Session state ----------
    if "memory" not in st.session_state:
        st.session_state.memory = Memory(total_frames=4, policy="FIFO")
        st.session_state.auto = False
        st.session_state.running = False
        st.session_state.last_auto_tick = time.time()

    memory = st.session_state.memory

    # ==================== Sidebar ====================
    with st.sidebar:
        st.markdown("## ⚙️ Configuration")
        total_frames = st.number_input("Total Frames", min_value=1, max_value=32, value=memory.total_frames)
        policy = st.selectbox("Replacement Policy", ["FIFO", "LRU"],
                              index=0 if memory.policy == "FIFO" else 1)
        if st.button("✅ Apply Settings", use_container_width=True):
            st.session_state.memory = Memory(total_frames=total_frames, policy=policy)
            memory = st.session_state.memory
            st.session_state.running = False
            st.session_state.auto = False
            st.success(f"Applied: {policy} with {total_frames} frames")

        st.markdown("---")
        st.markdown("## 🖱️ Manual Access")
        pid_m = st.number_input("Process ID (PID)", min_value=1, value=1, step=1, key="pid_manual")
        page_m = st.number_input("Page Number", min_value=0, value=0, step=1, key="page_manual")
        if st.button("⚡ Access Page", use_container_width=True):
            result = memory.allocate_page(int(pid_m), int(page_m))
            if result:
                st.success("Page Hit ✅")
            else:
                st.warning("Page Fault ⚠️")

        st.markdown("---")
        st.markdown("## 🤖 Auto Simulation")
        auto_interval_ms = st.slider("Interval (ms)", min_value=200, max_value=5000,
                                     value=1000, step=100)
        col_a, col_b = st.columns(2)
        with col_a:
            if not st.session_state.running:
                if st.button("▶ Start", use_container_width=True):
                    st.session_state.running = True
                    st.session_state.auto = True
        with col_b:
            if st.session_state.running:
                if st.button("⏹ Stop", use_container_width=True):
                    st.session_state.running = False
                    st.session_state.auto = False

        st.markdown("---")
        st.markdown("## 🗑️ Remove Page")
        rem_pid  = st.number_input("PID", min_value=1, value=1, step=1, key="rem_pid")
        rem_page = st.number_input("Page", min_value=0, value=0, step=1, key="rem_page")
        if st.button("Remove", use_container_width=True):
            memory.remove_page(int(rem_pid), int(rem_page))
            st.info(f"Removed PID {rem_pid} Page {rem_page}")

        st.markdown("---")
        if st.button("🔄 Reset Simulation", use_container_width=True):
            st.session_state.memory = Memory(total_frames=memory.total_frames, policy=memory.policy)
            st.session_state.running = False
            st.session_state.auto = False
            memory = st.session_state.memory
            st.success("Simulation reset!")

    # ==================== Auto-refresh ====================
    if st.session_state.auto:
        if HAS_AUTORELOAD and st_autorefresh is not None:
            st_autorefresh(interval=auto_interval_ms, limit=None, key="auto_refresh")
            pid_r = random.randint(1, 3)
            page_r = random.randint(0, max(4, memory.total_frames + 1))
            memory.allocate_page(pid_r, page_r)
        else:
            now = time.time()
            if now - st.session_state.last_auto_tick >= (auto_interval_ms / 1000.0):
                st.session_state.last_auto_tick = now
                pid_r = random.randint(1, 3)
                page_r = random.randint(0, max(4, memory.total_frames + 1))
                memory.allocate_page(pid_r, page_r)
                st.rerun()

    # ==================== Top KPI row ====================
    stats = memory.stats()
    k1, k2, k3, k4, k5 = st.columns(5)

    def kpi_card(col, label, value, sub="", color="#6C63FF"):
        col.markdown(f"""
        <div class="metric-card">
          <div class="label">{label}</div>
          <div class="value" style="color:{color};">{value}</div>
          <div class="sub" style="color:{color}99;">{sub}</div>
        </div>
        """, unsafe_allow_html=True)

    kpi_card(k1, "Total Accesses", stats["Total Accesses"])
    kpi_card(k2, "Page Hits",   stats["Page Hits"],   color="#43C59E")
    kpi_card(k3, "Page Faults", stats["Page Faults"], color="#F9A826")
    kpi_card(k4, "Hit Ratio",   f"{stats['Hit Ratio']*100:.1f}%",  color="#6C63FF")
    kpi_card(k5, "Fault Ratio", f"{stats['Fault Ratio']*100:.1f}%", color="#FF6584")

    # Hit / Fault progress bars
    if stats["Total Accesses"] > 0:
        bar_col1, bar_col2 = st.columns(2)
        with bar_col1:
            st.caption("🟢 Hit Ratio")
            st.progress(stats["Hit Ratio"])
        with bar_col2:
            st.caption("🟡 Fault Ratio")
            st.progress(stats["Fault Ratio"])

    st.markdown("<br>", unsafe_allow_html=True)

    # ==================== Main layout ====================
    left_col, right_col = st.columns([3, 2])

    # -------- LEFT: Frames + Charts --------
    with left_col:
        st.markdown('<div class="section-header">📦 Memory Frames</div>', unsafe_allow_html=True)

        # Responsive grid: max MAX_FRAMES_PER_ROW per row
        max_per_row = min(memory.total_frames, MAX_FRAMES_PER_ROW)
        cols_per_row = st.columns(max_per_row)
        for i, frame in enumerate(memory.frames):
            col = cols_per_row[i % max_per_row]
            if i != 0 and i % max_per_row == 0:
                cols_per_row = st.columns(max_per_row)
                col = cols_per_row[i % max_per_row]
            with col:
                if frame is not None:
                    fpid, fpage = frame
                    color = pid_color(fpid)
                    st.markdown(f"""
                    <div class="frame-card" style="background:{color}22; border-color:{color};">
                      <div class="frame-id">Frame {i}</div>
                      <div class="frame-pid" style="color:{color};">PID {fpid}</div>
                      <div class="frame-pg">Page {fpage}</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="frame-card" style="background:#1A1D2E; border-color:#2D2F45; border-style:dashed;">
                      <div class="frame-id">Frame {i}</div>
                      <div class="frame-pid" style="color:#3D3F55;">——</div>
                      <div class="frame-pg" style="color:#3D3F55;">empty</div>
                    </div>
                    """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ---- Frame occupancy matplotlib bar chart ----
        st.markdown('<div class="section-header">📊 Frame Occupancy</div>', unsafe_allow_html=True)
        fig_occ, ax_occ = plt.subplots(figsize=(max(4, memory.total_frames * 0.7), 2.5))
        fig_occ.patch.set_facecolor("#1A1D2E")
        ax_occ.set_facecolor("#1A1D2E")
        bar_colors = []
        for f in memory.frames:
            if f is None:
                bar_colors.append("#2D2F45")
            else:
                bar_colors.append(pid_color(f[0]))
        bar_labels = [f"F{i}" for i in range(memory.total_frames)]
        bar_vals   = [0 if f is None else 1 for f in memory.frames]
        ax_occ.bar(bar_labels, bar_vals, color=bar_colors, edgecolor="#0E1117", linewidth=0.8, width=0.6)
        ax_occ.set_ylim(0, 1.3)
        ax_occ.set_yticks([])
        ax_occ.tick_params(colors="#9395A5", labelsize=9)
        for spine in ax_occ.spines.values():
            spine.set_edgecolor("#2D2F45")
        ax_occ.set_title("Occupied (coloured) vs Empty (grey)", color="#9395A5", fontsize=9, pad=6)
        st.pyplot(fig_occ)
        plt.close(fig_occ)

        st.markdown("<br>", unsafe_allow_html=True)

        # ---- Pie chart ----
        st.markdown('<div class="section-header">🥧 Hit / Fault Breakdown</div>', unsafe_allow_html=True)
        if stats["Total Accesses"] == 0:
            st.info("No page accesses yet — trigger some accesses to see the chart.")
        else:
            fig_pie, ax_pie = plt.subplots(figsize=(4, 3))
            fig_pie.patch.set_facecolor("#1A1D2E")
            ax_pie.set_facecolor("#1A1D2E")
            sizes  = [stats["Page Hits"], stats["Page Faults"]]
            colors = ["#43C59E", "#F9A826"]
            explode = (0.05, 0)
            wedges, texts, autotexts = ax_pie.pie(
                sizes, explode=explode, labels=["Hits", "Faults"],
                autopct="%1.1f%%", startangle=90,
                colors=colors, textprops={"color": "#FAFAFA", "fontsize": 10}
            )
            for at in autotexts:
                at.set_color("#FAFAFA")
            ax_pie.axis("equal")
            st.pyplot(fig_pie)
            plt.close(fig_pie)

        # ---- Hits/Faults over time ----
        if len(memory.history_hits) > 1:
            st.markdown('<div class="section-header">📈 Cumulative Hits & Faults Over Time</div>',
                        unsafe_allow_html=True)
            fig_hist, ax_hist = plt.subplots(figsize=(6, 2.5))
            fig_hist.patch.set_facecolor("#1A1D2E")
            ax_hist.set_facecolor("#1A1D2E")
            xs = list(range(1, len(memory.history_hits) + 1))
            ax_hist.plot(xs, memory.history_hits,  color="#43C59E", linewidth=1.8, label="Hits")
            ax_hist.plot(xs, memory.history_faults, color="#F9A826", linewidth=1.8, label="Faults")
            ax_hist.fill_between(xs, memory.history_hits,  alpha=0.15, color="#43C59E")
            ax_hist.fill_between(xs, memory.history_faults, alpha=0.15, color="#F9A826")
            ax_hist.tick_params(colors="#9395A5", labelsize=8)
            ax_hist.legend(facecolor="#1A1D2E", labelcolor="#FAFAFA", fontsize=9)
            for spine in ax_hist.spines.values():
                spine.set_edgecolor("#2D2F45")
            st.pyplot(fig_hist)
            plt.close(fig_hist)

    # -------- RIGHT: Stats + Page Table + Log --------
    with right_col:
        # ---- Page Table ----
        st.markdown('<div class="section-header">🗂️ Page Table</div>', unsafe_allow_html=True)
        pt_rows = []
        for p, pages in memory.page_table.items():
            pt_rows.append({
                "PID": p,
                "Pages in Memory": ", ".join(map(str, sorted(pages))) if pages else "—",
            })
        if pt_rows:
            df_pt = pd.DataFrame(pt_rows)
            st.dataframe(df_pt, use_container_width=True, hide_index=True)
        else:
            st.caption("No page mappings yet.")

        # ---- Replacement queue ----
        st.markdown('<div class="section-header">🔄 Replacement Queue</div>', unsafe_allow_html=True)
        if memory.policy == "FIFO":
            rep_list = list(memory.replacement.queue)
        else:
            rep_list = list(memory.replacement.pages.keys())

        if rep_list:
            for idx, entry in enumerate(rep_list):
                label = "👈 next victim" if idx == 0 else ""
                st.markdown(
                    f"`PID {entry[0]} · Page {entry[1]}`  "
                    f"<span style='color:#FF6584;font-size:0.75rem;'>{label}</span>",
                    unsafe_allow_html=True
                )
        else:
            st.caption("Queue is empty.")

        # ---- Activity log ----
        st.markdown('<div class="section-header">📋 Activity Log</div>', unsafe_allow_html=True)
        log_lines = list(reversed(memory.logs[-LOG_DISPLAY_LIMIT:]))
        log_html = ""
        for line in log_lines:
            if "HIT" in line:
                log_html += f'<div class="log-hit">{line}</div>'
            elif "FAULT" in line:
                log_html += f'<div class="log-fault">{line}</div>'
            elif "Removed" in line:
                log_html += f'<div class="log-remove">{line}</div>'
            else:
                log_html += f'<div class="log-info">{line}</div>'
        st.markdown(log_html, unsafe_allow_html=True)

else:
    # CLI fallback
    print("Streamlit not installed. Run CLI or install with: pip install streamlit")
    mem = Memory(total_frames=4, policy="FIFO")
    print("Minimal CLI demo: allocating (1,0), (1,1), (2,0), (1,0) ...")
    mem.allocate_page(1, 0)
    mem.allocate_page(1, 1)
    mem.allocate_page(2, 0)
    mem.allocate_page(1, 0)
    print("Stats:", mem.stats())
