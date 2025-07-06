# File: flashcard-telegram-bot/services/chart_service.py
"""
Module chứa business logic liên quan đến việc tạo biểu đồ thống kê.
(Sửa lần 6: Tạo một biểu đồ kết hợp duy nhất với 3 chỉ số hoạt động hàng ngày,
             mỗi chỉ số có đường trung bình tổng thể (ngang).
             Hiển thị điểm Cao nhất/Thấp nhất cho mỗi chỉ số.
             Loại bỏ các hàm vẽ biểu đồ riêng lẻ và biểu đồ tổng điểm.)
"""
import logging
import os
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import matplotlib.dates as mdates 
from datetime import datetime, timedelta 
import time
import numpy as np 
# import pandas as pd # Không cần pandas nữa nếu chỉ tính overall average

import config 
from database.query_stats import get_daily_activity_history_by_user

logger = logging.getLogger(__name__)

def generate_combined_daily_activity_chart(user_id_db, user_timezone_offset, num_days=None):
    """
    Tạo một biểu đồ kết hợp thể hiện Điểm, Thẻ mới, và Lượt ôn tập hàng ngày.
    Mỗi chỉ số sẽ có đường trung bình tổng thể (đường ngang).
    Hiển thị điểm Cao nhất và Thấp nhất cho mỗi chỉ số.
    """
    log_prefix = f"[CHART_SERVICE_COMBINED_DAILY|UserDBID:{user_id_db}]"
    logger.info(f"{log_prefix} Bắt đầu tạo biểu đồ kết hợp hoạt động hàng ngày (num_days: {num_days}).")

    try:
        daily_history = get_daily_activity_history_by_user(user_id_db, user_timezone_offset)
        if not daily_history:
            logger.info(f"{log_prefix} Không có dữ liệu lịch sử hoạt động.")
            return None

        sorted_history = sorted(daily_history.items())
        history_to_plot = sorted_history
        if num_days is not None and isinstance(num_days, int) and num_days > 0:
            if len(sorted_history) > num_days: 
                history_to_plot = sorted_history[-num_days:]
        
        if not history_to_plot or len(history_to_plot) < 1: 
            logger.info(f"{log_prefix} Không đủ dữ liệu lịch sử để vẽ biểu đồ kết hợp.")
            return None

        dates_dt = []
        scores_daily = []
        new_cards_daily = []
        reviewed_counts_daily = []

        for date_str, stats in history_to_plot:
            try:
                dates_dt.append(datetime.strptime(date_str, '%Y-%m-%d'))
                scores_daily.append(stats.get('score', 0))
                new_cards_daily.append(stats.get('new', 0))
                reviewed_counts_daily.append(stats.get('reviewed', 0))
            except ValueError:
                logger.warning(f"{log_prefix} Lỗi parse ngày: {date_str}. Bỏ qua.")
                continue
        
        if not dates_dt : 
            logger.info(f"{log_prefix} Không có dữ liệu ngày hợp lệ để vẽ.")
            return None
        
        # Đảm bảo các list dữ liệu có cùng độ dài với dates_dt, nếu không có dữ liệu thì fill bằng 0
        # Điều này quan trọng nếu một số ngày không có hoạt động nào cả (get_daily_activity_history_by_user có thể trả về thiếu ngày)
        # Tuy nhiên, get_daily_activity_history_by_user hiện tại trả về defaultdict, nên các ngày thiếu sẽ có giá trị 0.

        np_scores = np.array(scores_daily) if scores_daily else np.array([0])
        np_new_cards = np.array(new_cards_daily) if new_cards_daily else np.array([0])
        np_reviewed = np.array(reviewed_counts_daily) if reviewed_counts_daily else np.array([0])

        avg_score = np.mean(np_scores) if len(np_scores) > 0 else 0
        avg_new_cards = np.mean(np_new_cards) if len(np_new_cards) > 0 else 0
        avg_reviewed = np.mean(np_reviewed) if len(np_reviewed) > 0 else 0

        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax1 = plt.subplots(figsize=(15, 8)) 
        history_range_str = f"(Toàn bộ LS)" if num_days is None else f"({len(history_to_plot)} ngày gần nhất)"
        fig.suptitle(f"Biểu đồ Hoạt động Hàng ngày Kết hợp {history_range_str}", fontsize=16, y=0.98)

        # --- Trục Y1 cho Điểm ---
        color_score = 'dodgerblue'
        ax1.set_xlabel("Ngày", fontsize=12)
        ax1.set_ylabel("Điểm kiếm được", color=color_score, fontsize=12)
        if len(dates_dt) == len(np_scores) and len(dates_dt) >=1:
            ax1.plot(dates_dt, np_scores, color=color_score, linestyle='-', linewidth=2, label='Điểm/ngày', zorder=2, alpha=0.9)
            ax1.axhline(avg_score, color=color_score, linestyle='--', linewidth=1.5, label=f'TB Điểm: {avg_score:.1f}', zorder=1, alpha=0.7)
            if len(np_scores) > 0:
                max_s = np_scores.max(); min_s = np_scores.min()
                idx_max_s = np.argmax(np_scores); idx_min_s = np.argmin(np_scores)
                if 0 <= idx_max_s < len(dates_dt):
                    date_max_s = dates_dt[idx_max_s]
                    ax1.plot(date_max_s, max_s, 'o', color='red', markersize=6, zorder=3)
                    ax1.annotate(f"Cao nhất: {max_s}", xy=(date_max_s, max_s), xytext=(3,3), textcoords='offset points', ha='left', va='bottom', fontsize=8, color='red', bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.7))
                if 0 <= idx_min_s < len(dates_dt) and (min_s != max_s or idx_min_s != idx_max_s):
                    date_min_s = dates_dt[idx_min_s]
                    ax1.plot(date_min_s, min_s, 'o', color='darkred', markersize=6, zorder=3)
                    ax1.annotate(f"Thấp nhất: {min_s}", xy=(date_min_s, min_s), xytext=(3,-10), textcoords='offset points', ha='left', va='top', fontsize=8, color='darkred', bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.7))
        ax1.tick_params(axis='y', labelcolor=color_score)
        
        # --- Trục Y2 cho Thẻ mới và Lượt ôn ---
        ax2 = ax1.twinx()
        color_new = 'mediumseagreen'; color_reviewed = 'salmon'
        ax2.set_ylabel("Số lượng (Thẻ mới/Lượt ôn)", color='dimgray', fontsize=12)
        
        if len(dates_dt) == len(np_new_cards) and len(dates_dt) >=1:
            ax2.plot(dates_dt, np_new_cards, color=color_new, linestyle='-', linewidth=2, label='Thẻ mới/ngày', zorder=2, alpha=0.9)
            ax2.axhline(avg_new_cards, color=color_new, linestyle='--', linewidth=1.5, label=f'TB Thẻ mới: {avg_new_cards:.1f}', zorder=1, alpha=0.7)
            if len(np_new_cards) > 0:
                max_n = np_new_cards.max(); min_n = np_new_cards.min()
                idx_max_n = np.argmax(np_new_cards); idx_min_n = np.argmin(np_new_cards)
                if 0 <= idx_max_n < len(dates_dt):
                    date_max_n = dates_dt[idx_max_n]
                    ax2.plot(date_max_n, max_n, 'P', color='darkgreen', markersize=6, zorder=3)
                    ax2.annotate(f"CN: {max_n}", xy=(date_max_n, max_n), xytext=(3,3), textcoords='offset points', ha='left', va='bottom', fontsize=8, color='darkgreen', bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.7))
                if 0 <= idx_min_n < len(dates_dt) and (min_n != max_n or idx_min_n != idx_max_n):
                    date_min_n = dates_dt[idx_min_n]
                    ax2.plot(date_min_n, min_n, 'X', color='darkgreen', markersize=6, zorder=3)
                    ax2.annotate(f"TN: {min_n}", xy=(date_min_n, min_n), xytext=(3,-10), textcoords='offset points', ha='left', va='top', fontsize=8, color='darkgreen', bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.7))

        if len(dates_dt) == len(np_reviewed) and len(dates_dt) >=1:
            ax2.plot(dates_dt, np_reviewed, color=color_reviewed, linestyle='-', linewidth=2, label='Lượt ôn/ngày', zorder=2, alpha=0.9)
            ax2.axhline(avg_reviewed, color=color_reviewed, linestyle='--', linewidth=1.5, label=f'TB Lượt ôn: {avg_reviewed:.1f}', zorder=1, alpha=0.7)
            if len(np_reviewed) > 0:
                max_r = np_reviewed.max(); min_r = np_reviewed.min()
                idx_max_r = np.argmax(np_reviewed); idx_min_r = np.argmin(np_reviewed)
                if 0 <= idx_max_r < len(dates_dt):
                    date_max_r = dates_dt[idx_max_r]
                    ax2.plot(date_max_r, max_r, 'P', color='darkred', markersize=6, zorder=3)
                    ax2.annotate(f"CN: {max_r}", xy=(date_max_r, max_r), xytext=(3,3), textcoords='offset points', ha='left', va='bottom', fontsize=8, color='darkred', bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.7))
                if 0 <= idx_min_r < len(dates_dt) and (min_r != max_r or idx_min_r != idx_max_r):
                    date_min_r = dates_dt[idx_min_r]
                    ax2.plot(date_min_r, min_r, 'X', color='maroon', markersize=6, zorder=3)
                    ax2.annotate(f"TN: {min_r}", xy=(date_min_r, min_r), xytext=(3,-10), textcoords='offset points', ha='left', va='top', fontsize=8, color='maroon', bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.7))
        ax2.tick_params(axis='y', labelcolor='dimgray')
        
        if len(np_new_cards) > 0 or len(np_reviewed) > 0:
            all_counts = []
            if len(np_new_cards) > 0: all_counts.extend(np_new_cards)
            if len(np_reviewed) > 0: all_counts.extend(np_reviewed)
            if all_counts:
                 min_y2_val = min(all_counts) if all_counts else 0
                 if min_y2_val >= 0: ax2.set_ylim(bottom=0) # Đảm bảo trục Y2 bắt đầu từ 0 nếu tất cả giá trị >=0

        locator = mdates.AutoDateLocator(minticks=5, maxticks=15) 
        formatter = mdates.ConciseDateFormatter(locator)
        ax1.xaxis.set_major_locator(locator); ax1.xaxis.set_major_formatter(formatter)
        fig.autofmt_xdate(rotation=25, ha='right') 

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=9, ncol=2)
        
        ax1.grid(True, linestyle=':', alpha=0.4, axis='x') 

        fig.tight_layout(rect=[0, 0.03, 1, 0.93]) 
        timestamp_file = int(time.time())
        filename = f"combined_daily_activity_chart_{user_id_db}_{timestamp_file}.png"
        output_path = os.path.join(config.TEMP_CHARTS_DIR, filename)
        os.makedirs(config.TEMP_CHARTS_DIR, exist_ok=True)
        plt.savefig(output_path, dpi=120); plt.close(fig) 
        logger.info(f"{log_prefix} Đã lưu biểu đồ kết hợp vào: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi khi tạo biểu đồ kết hợp: {e}", exc_info=True)
        try: plt.close(fig) 
        except: pass
        return None

# Các hàm generate_daily_activity_chart và generate_total_score_chart đã bị loại bỏ.
