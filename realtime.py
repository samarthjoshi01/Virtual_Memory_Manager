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
    print("Streamlit imported successfully")
    try:
        from streamlit_autorefresh import st_autorefresh
        HAS_AUTORELOAD = True
        print("Autorefresh imported successfully")
    except Exception as e:
        print("Autorefresh error:", e)
        st_autorefresh = None
        HAS_AUTORELOAD = False
    ST_AVAILABLE = True
except Exception as e:
    print("Streamlit error:", e)
    ST_AVAILABLE = False


# visualization libs
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

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
        # add or update
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
        self.set_policy(policy)

    def set_policy(self, policy):
        self.policy = policy.upper()
        self.replacement = LRUReplacement() if self.policy == "LRU" else FIFOReplacement()
        self.log(f"Policy set to {self.policy}")

    def log(self, text):
        ts = time.strftime("%H:%M:%S")
        self.logs.append(f"[{ts}] {text}")
        # keep logs bounded
        if len(self.logs) > 1000:
            self.logs = self.logs[-1000:]

    def allocate_page(self, pid, page):
        page_tuple = (pid, page)
        # hit
        if page_tuple in self.frames:
            self.page_hits += 1
            self.replacement.access_page(page_tuple)
            self.log(f"HIT: {page_tuple}")
            return True
        # fault
        self.page_faults += 1
        self.log(f"FAULT: {page_tuple}")
        if self.free_frames:
            frame = self.free_frames.pop(0)
            self.frames[frame] = page_tuple
            self.page_table.setdefault(pid, set()).add(page)
            self.replacement.add_page(page_tuple)
            self.log(f"Allocated {page_tuple} -> Frame {frame}")
        else:
            victim = self.replacement.evict_page()
            try:
                victim_frame = self.frames.index(victim)
            except ValueError:
                # fallback: pick frame 0 if victim not found (shouldn't happen)
                victim_frame = 0
            old_pid, old_page = victim
            # remove old mapping safely
            if old_pid in self.page_table and old_page in self.page_table[old_pid]:
                self.page_table[old_pid].remove(old_page)
            self.frames[victim_frame] = page_tuple
            self.page_table.setdefault(pid, set()).add(page)
            self.replacement.add_page(page_tuple)
            self.log(f"Evicted {victim} -> Inserted {page_tuple} in Frame {victim_frame}")
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
            self.log(f"Removed {page_tuple} from Frame {idx}")

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

# ------------------------- Streamlit UI -------------------------
if ST_AVAILABLE:
    st.set_page_config(page_title="VMM Real-Time Visualizer", layout="wide")
    st.title("🕒 Virtual Memory Manager — Real-Time Visualization")

    # initialize in session state
    if 'memory' not in st.session_state:
        st.session_state.memory = Memory(total_frames=4, policy="FIFO")
        st.session_state.auto = False
        st.session_state.running = False
        st.session_state.last_auto_tick = time.time()

    memory = st.session_state.memory

    # Sidebar configuration
    with st.sidebar:
        st.header("Configuration")
        total_frames = st.number_input("Total Frames", min_value=1, max_value=32, value=memory.total_frames)
        policy = st.selectbox("Policy", ["FIFO", "LRU"], index=0 if memory.policy == "FIFO" else 1)
        if st.button("Apply"):
            st.session_state.memory = Memory(total_frames=total_frames, policy=policy)
            memory = st.session_state.memory
            st.session_state.running = False
            st.session_state.auto = False
            st.success(f"Applied: {policy} with {total_frames} frames")

        st.markdown("---")
        st.header("Manual Simulation Controls")
        pid = st.number_input("PID (manual)", min_value=1, value=1, step=1, key="pid_manual")
        access_page = st.number_input("Access Page (manual)", min_value=0, value=0, step=1, key="page_manual")

        if st.button("Access Once (manual)"):
            memory.allocate_page(int(pid), int(access_page))

        st.markdown("---")
        st.header("Auto Simulation")
        if not st.session_state.running and st.button("Start Real-Time Simulation"):
            st.session_state.running = True
            st.session_state.auto = True
        elif st.session_state.running and st.button("Stop Simulation"):
            st.session_state.running = False
            st.session_state.auto = False

        st.markdown("Auto settings")
        auto_interval_ms = st.number_input("Auto interval (ms)", min_value=200, max_value=10000, value=1000, step=100)

        st.markdown("---")
        st.header("Page Management")
        remove_pid = st.number_input("PID to remove (optional)", min_value=1, value=1, step=1, key="rem_pid")
        remove_page = st.number_input("Page to remove (optional)", min_value=0, value=0, step=1, key="rem_page")
        if st.button("Remove Page"):
            memory.remove_page(int(remove_pid), int(remove_page))

    # Auto refresh / auto-simulate
    if st.session_state.auto:
        if HAS_AUTORELOAD and st_autorefresh is not None:
            # trigger streamlit to rerun periodically
            st_autorefresh(interval=auto_interval_ms, limit=None, key="auto_refresh")
            # on each rerun, do a random allocation
            pid = random.randint(1, 3)
            page = random.randint(0, max(4, memory.total_frames + 1))
            memory.allocate_page(pid, page)
        else:
            # fallback: use a simple time check and st.experimental_rerun
            now = time.time()
            if now - st.session_state.last_auto_tick >= (auto_interval_ms / 1000.0):
                st.session_state.last_auto_tick = now
                pid = random.randint(1, 3)
                page = random.randint(0, max(4, memory.total_frames + 1))
                memory.allocate_page(pid, page)
                # trigger rerun
                st.experimental_rerun()

    # Layout: left = memory frames + charts, right = stats + logs
    left_col, right_col = st.columns([2, 1])

    # Memory frames visualization
    with left_col:
        st.subheader("Memory Frames")
        frame_labels = []
        frame_values = []
        for i, frame in enumerate(memory.frames):
            label = f"Frame {i}"
            frame_labels.append(label)
            frame_values.append(str(frame) if frame else "_empty_")

        # show simple textual display in columns
        cols = st.columns(memory.total_frames)
        for i, frame in enumerate(memory.frames):
            with cols[i]:
                st.markdown(f"**Frame {i}:**")
                st.write(frame if frame else "_empty_")

        st.markdown("---")

        # Frame occupancy bar chart (1 if occupied else 0)
        occupancy = [0 if f is None else 1 for f in memory.frames]
        df_frames = pd.DataFrame({
            "frame": [f"F{i}" for i in range(memory.total_frames)],
            "occupied": occupancy,
            "content": [str(f) if f else "_empty_" for f in memory.frames],
        })
        st.subheader("Frame Occupancy")
        # Use altair-backed st.bar_chart (pandas) for simplicity
        st.bar_chart(df_frames.set_index("frame")["occupied"])

        st.markdown("---")
        # Pie chart: Hits vs Faults with percentages
        st.subheader("Hit / Fault Breakdown")

        stats = memory.stats()
        hits = stats["Page Hits"]
        faults = stats["Page Faults"]
        total = stats["Total Accesses"]

        # safe pie fallback when total == 0
        if total == 0:
            st.info("No page accesses yet. Trigger some accesses to see the pie chart.")
        else:
            labels = ["Hits", "Faults"]
            sizes = [hits, faults]

            fig1, ax1 = plt.subplots()
            explode = (0.05, 0)  # slightly separate the first slice
            # autopct shows percentage; format to 1 decimal place
            ax1.pie(sizes, explode=explode, labels=labels, autopct="%1.1f%%", startangle=90, shadow=False)
            ax1.axis("equal")  # Equal aspect ratio ensures the pie chart is circular.
            st.pyplot(fig1)

        st.markdown("---")
        # show a small timeline of last few log lines
        st.subheader("Recent Activity")
        for log in reversed(memory.logs[-20:]):
            st.write(log)

    # Right column: numeric stats and tables
    with right_col:
        st.subheader("Statistics")
        stats = memory.stats()
        st.metric("Total Accesses", stats["Total Accesses"])
        st.metric("Page Hits", stats["Page Hits"], delta=None)
        st.metric("Page Faults", stats["Page Faults"], delta=None)
        st.write(f"Hit Ratio: {stats['Hit Ratio']*100:.1f}%")
        st.write(f"Fault Ratio: {stats['Fault Ratio']*100:.1f}%")

        st.markdown("---")
        st.subheader("Page Table (summary)")
        # show page table as dataframe
        page_table_summary = []
        for pid, pages in memory.page_table.items():
            page_table_summary.append({"PID": pid, "Pages": ",".join(map(str, sorted(pages))) if pages else ""})
        if page_table_summary:
            df_pt = pd.DataFrame(page_table_summary)
            st.dataframe(df_pt)
        else:
            st.write("No mappings yet.")

        st.markdown("---")
        st.subheader("Replacement Structure (internal view)")
        # show the replacement structure content
        if isinstance(memory.replacement, FIFOReplacement):
            rep_list = list(memory.replacement.queue)
        else:
            # Get current pages depending on policy
            if memory.policy == "LRU":
                rep_list = list(memory.replacement.pages.keys())
            else:  # FIFO
                rep_list = list(memory.replacement.queue)

        st.write("Order (victim -> ...):")
        if rep_list:
            for r in rep_list:
                st.write(str(r))
        else:
            st.write("_empty_")

else:
    # CLI fallback
    print("Streamlit not installed. Run CLI or install with: pip install streamlit")
    # minimal CLI demo
    mem = Memory(total_frames=4, policy="FIFO")
    print("Minimal CLI demo: allocating (1,0), (1,1), (2,0), (1,0) ...")
    mem.allocate_page(1, 0)
    mem.allocate_page(1, 1)
    mem.allocate_page(2, 0)
    mem.allocate_page(1, 0)
    print("Stats:", mem.stats())
