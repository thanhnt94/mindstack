# Path: flashcard_v2/services/reporting_service.py
"""
Module chứa business logic cho chức năng báo cáo lỗi thẻ.
(Đã thêm lấy reporter_telegram_id)
(Đã sửa lỗi thiếu import)
"""

import logging
import time
import asyncio
import sqlite3 # <<< THÊM IMPORT SQLITE3

# Import các module query database cần thiết
from database.connection import database_connect # <<< THÊM IMPORT database_connect
from database.query_report import (
    add_card_report,
    get_sets_with_pending_reports,
    get_pending_reports_for_set,
    update_report_status,
    get_report_details_by_id,
    get_pending_reports_summary_by_card, # Hàm query mới
    update_status_for_card_reports # Hàm query mới
)
from database.query_card import get_card_by_id
from database.query_set import get_sets
from database.query_user import get_user_by_id # Import hàm mới

# Import exceptions
from utils.exceptions import (
    DatabaseError,
    CardNotFoundError,
    SetNotFoundError,
    UserNotFoundError,
    ValidationError,
    DuplicateError
)

logger = logging.getLogger(__name__)

# ... (Nội dung các hàm submit_card_report, get_reportable_sets_summary,
#      get_report_summary_by_card_in_set, get_pending_reports_for_card,
#      resolve_all_reports_for_card, resolve_card_report giữ nguyên như phiên bản trước) ...

async def submit_card_report(flashcard_id, reporter_user_id, report_text):
    """
    Xử lý logic khi người dùng gửi báo cáo lỗi cho một thẻ.
    Lấy thông tin cần thiết, lưu vào DB và trả về thông tin để gửi thông báo.
    """
    log_prefix = f"[SERVICE_REPORT_SUBMIT|Card:{flashcard_id}|Reporter:{reporter_user_id}]"
    logger.info(f"{log_prefix} Bắt đầu xử lý submit báo cáo.")

    try:
        # 1. Lấy thông tin thẻ để biết set_id
        logger.debug(f"{log_prefix} Lấy thông tin thẻ...")
        card_info = get_card_by_id(flashcard_id)
        set_id = card_info.get('set_id')
        if set_id is None:
            raise DatabaseError(f"Thẻ {flashcard_id} không có set_id.")
        logger.debug(f"{log_prefix} Thẻ thuộc Set ID: {set_id}")

        # 2. Lấy thông tin bộ thẻ để biết creator_user_id
        logger.debug(f"{log_prefix} Lấy thông tin bộ thẻ...")
        set_info_list, _ = get_sets(set_id=set_id)
        if not set_info_list:
            raise SetNotFoundError(set_id=set_id)
        creator_user_id = set_info_list[0].get('creator_user_id')
        logger.debug(f"{log_prefix} Người tạo bộ thẻ User ID: {creator_user_id}")

        # 3. Thêm báo cáo vào database
        logger.debug(f"{log_prefix} Thêm báo cáo vào DB...")
        report_id = add_card_report(
            flashcard_id=flashcard_id,
            reporter_user_id=reporter_user_id,
            creator_user_id=creator_user_id,
            set_id=set_id,
            report_text=report_text
        )
        logger.info(f"{log_prefix} Đã thêm báo cáo với ID: {report_id}")

        # 4. Trả về thông tin cần thiết cho handler
        result_data = {
            'report_id': report_id,
            'creator_user_id': creator_user_id,
            'set_id': set_id,
            'card_info': card_info
        }
        return result_data

    except (CardNotFoundError, SetNotFoundError, ValidationError, DuplicateError, DatabaseError) as e:
        logger.error(f"{log_prefix} Lỗi đã biết khi xử lý submit báo cáo: {e}")
        raise e
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi không mong muốn khi xử lý submit báo cáo: {e}")
        raise DatabaseError("Lỗi không mong muốn khi xử lý submit báo cáo.", original_exception=e)


async def get_reportable_sets_summary(creator_user_id):
    """
    Lấy danh sách tóm tắt các bộ từ có báo cáo lỗi đang chờ xử lý cho người tạo.
    """
    log_prefix = f"[SERVICE_GET_REPORTABLE_SETS|Creator:{creator_user_id}]"
    logger.debug(f"{log_prefix} Lấy danh sách tóm tắt bộ có báo cáo.")
    try:
        sets_summary = get_sets_with_pending_reports(creator_user_id)
        return sets_summary
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn khi lấy tóm tắt báo cáo theo bộ: {e}", exc_info=True)
        raise DatabaseError("Lỗi không mong muốn khi lấy tóm tắt báo cáo.", original_exception=e)


async def get_report_summary_by_card_in_set(set_id, creator_user_id):
    """
    Lấy danh sách tóm tắt các thẻ có báo cáo lỗi đang chờ xử lý cho một bộ từ.
    """
    log_prefix = f"[SERVICE_GET_CARD_SUMMARY|Set:{set_id}|Creator:{creator_user_id}]"
    logger.debug(f"{log_prefix} Lấy tóm tắt báo cáo theo thẻ.")
    try:
        summary = get_pending_reports_summary_by_card(set_id, creator_user_id)
        return summary
    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn khi lấy tóm tắt báo cáo theo thẻ: {e}", exc_info=True)
        raise DatabaseError("Lỗi không mong muốn khi lấy tóm tắt báo cáo theo thẻ.", original_exception=e)


async def get_pending_reports_for_card(flashcard_id, creator_user_id):
    """
    Lấy danh sách chi tiết các báo cáo lỗi đang chờ xử lý cho một flashcard cụ thể,
    kèm theo telegram_id của người báo cáo.
    """
    log_prefix = f"[SERVICE_GET_CARD_REPORTS|Card:{flashcard_id}|Creator:{creator_user_id}]"
    logger.debug(f"{log_prefix} Lấy chi tiết báo cáo pending cho thẻ.")
    reports_with_telegram_id = []
    conn_reports = None # Khởi tạo conn_reports ở đây
    try:
        pending_reports_raw = []
        try:
            conn_reports = database_connect() # Sử dụng database_connect đã import
            if conn_reports is None:
                raise DatabaseError("Không thể kết nối DB")
            conn_reports.row_factory = sqlite3.Row # Sử dụng sqlite3 đã import
            cursor_reports = conn_reports.cursor()
            query_reports_for_card = """
                SELECT
                    cr.report_id, cr.flashcard_id, cr.reporter_user_id,
                    cr.report_text, cr.reported_at,
                    f.front
                FROM CardReports cr
                LEFT JOIN Flashcards f ON cr.flashcard_id = f.flashcard_id
                WHERE cr.flashcard_id = ? AND cr.creator_user_id = ? AND cr.status = 'pending'
                ORDER BY cr.reported_at ASC
            """
            cursor_reports.execute(query_reports_for_card, (flashcard_id, creator_user_id))
            pending_reports_raw = cursor_reports.fetchall()
            logger.info(f"{log_prefix} Tìm thấy {len(pending_reports_raw)} báo cáo thô cho thẻ.")
        finally:
            if conn_reports:
                conn_reports.close()

        user_info_cache = {}
        for report_row in pending_reports_raw:
            report_dict = dict(report_row)
            reporter_user_id = report_dict.get('reporter_user_id')
            reporter_telegram_id = None

            if reporter_user_id:
                if reporter_user_id in user_info_cache:
                    reporter_telegram_id = user_info_cache[reporter_user_id]
                    logger.debug(f"{log_prefix} Lấy reporter_telegram_id từ cache cho UID {reporter_user_id}: {reporter_telegram_id}")
                else:
                    try:
                        reporter_info = get_user_by_id(reporter_user_id)
                        if reporter_info:
                            reporter_telegram_id = reporter_info.get('telegram_id')
                            user_info_cache[reporter_user_id] = reporter_telegram_id
                            logger.debug(f"{log_prefix} Lấy và cache reporter_telegram_id cho UID {reporter_user_id}: {reporter_telegram_id}")
                        else:
                            user_info_cache[reporter_user_id] = None
                            logger.warning(f"{log_prefix} Không tìm thấy thông tin cho reporter_user_id {reporter_user_id}.")
                    except UserNotFoundError:
                        user_info_cache[reporter_user_id] = None
                        logger.warning(f"{log_prefix} UserNotFoundError cho reporter_user_id {reporter_user_id}.")
                    except DatabaseError as e_db_user:
                         logger.error(f"{log_prefix} Lỗi DB khi lấy thông tin reporter {reporter_user_id}: {e_db_user}")
                         user_info_cache[reporter_user_id] = None
                    except Exception as e_user:
                        logger.error(f"{log_prefix} Lỗi không mong muốn khi lấy thông tin reporter {reporter_user_id}: {e_user}", exc_info=True)
                        user_info_cache[reporter_user_id] = None

            report_dict['reporter_telegram_id'] = reporter_telegram_id
            reports_with_telegram_id.append(report_dict)

        return reports_with_telegram_id

    except Exception as e:
        logger.error(f"{log_prefix} Lỗi không mong muốn khi lấy chi tiết báo cáo cho thẻ: {e}", exc_info=True)
        raise DatabaseError("Lỗi không mong muốn khi lấy chi tiết báo cáo cho thẻ.", original_exception=e)


async def resolve_all_reports_for_card(flashcard_id, resolver_user_id):
    """
    Đánh dấu tất cả các báo cáo đang chờ xử lý cho một flashcard cụ thể là đã giải quyết.
    """
    log_prefix = f"[SERVICE_RESOLVE_CARD_REPORTS|CardID:{flashcard_id}|Resolver:{resolver_user_id}]"
    logger.info(f"{log_prefix} Đánh dấu tất cả báo cáo cho thẻ là đã giải quyết.")

    reporters_to_notify_set = set()
    updated_count = 0
    conn = None

    try:
        conn = database_connect() # Sử dụng database_connect đã import
        if conn is None:
            raise DatabaseError("Không thể kết nối DB.")
        conn.row_factory = sqlite3.Row # Sử dụng sqlite3 đã import

        with conn:
            cursor = conn.cursor()

            # 1. Lấy danh sách reporter_user_id
            query_reporters = """
                SELECT DISTINCT reporter_user_id
                FROM CardReports
                WHERE flashcard_id = ? AND status = 'pending' AND reporter_user_id IS NOT NULL
            """
            cursor.execute(query_reporters, (flashcard_id,))
            pending_reporter_user_ids = [row['reporter_user_id'] for row in cursor.fetchall()]
            logger.debug(f"{log_prefix} Tìm thấy {len(pending_reporter_user_ids)} user ID người báo cáo cần lấy telegram ID.")

            # 2. Lấy telegram_id
            if pending_reporter_user_ids:
                placeholders = ','.join('?' * len(pending_reporter_user_ids))
                query_telegram_ids = f"SELECT user_id, telegram_id FROM Users WHERE user_id IN ({placeholders})"
                cursor.execute(query_telegram_ids, pending_reporter_user_ids)
                for row in cursor.fetchall():
                    user_id_rep = row['user_id']
                    telegram_id_rep = row['telegram_id']
                    if telegram_id_rep:
                        reporters_to_notify_set.add(telegram_id_rep)
                    else:
                        logger.warning(f"{log_prefix} Không tìm thấy telegram_id cho reporter_user_id {user_id_rep}.")
                logger.info(f"{log_prefix} Thu thập được {len(reporters_to_notify_set)} telegram ID để thông báo.")

            # 3. Cập nhật trạng thái
            updated_count = update_status_for_card_reports(flashcard_id, 'resolved', resolver_user_id, conn=conn)

        logger.info(f"{log_prefix} Đã đánh dấu {updated_count} báo cáo cho thẻ {flashcard_id} là resolved.")

        return {
            'updated_count': updated_count,
            'reporters_to_notify': list(reporters_to_notify_set)
        }

    except (ValidationError, DatabaseError, sqlite3.Error) as e_resolve: # Sử dụng sqlite3 đã import
        logger.error(f"{log_prefix} Lỗi khi giải quyết báo cáo cho thẻ: {e_resolve}", exc_info=True)
        return None
    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi không mong muốn khi giải quyết báo cáo cho thẻ: {e}")
        return None
    finally:
        if conn:
            conn.close()
            logger.debug(f"{log_prefix} Đã đóng kết nối DB.")


async def resolve_card_report(report_id, resolver_user_id):
    """
    Xử lý việc đánh dấu một báo cáo lỗi là đã được giải quyết.
    """
    log_prefix = f"[SERVICE_RESOLVE_REPORT|ReportID:{report_id}|Resolver:{resolver_user_id}]"
    logger.info(f"{log_prefix} Đánh dấu báo cáo đã giải quyết.")

    try:
        # 1. Lấy thông tin báo cáo
        report_details = get_report_details_by_id(report_id)
        if not report_details:
            logger.warning(f"{log_prefix} Không tìm thấy báo cáo ID {report_id}.")
            return None

        reporter_user_id = report_details.get('reporter_user_id')

        # 2. Cập nhật trạng thái
        update_success = update_report_status(report_id, 'resolved', resolver_user_id)
        if not update_success:
            logger.error(f"{log_prefix} Cập nhật trạng thái report {report_id} thất bại.")
            return None

        # 3. Lấy telegram_id người báo cáo
        reporter_telegram_id = None
        if reporter_user_id:
            try:
                reporter_info = get_user_by_id(reporter_user_id)
                if reporter_info:
                    reporter_telegram_id = reporter_info.get('telegram_id')
            except UserNotFoundError:
                 logger.warning(f"{log_prefix} Không tìm thấy thông tin reporter_user_id {reporter_user_id}.")
            except Exception as e_get_reporter:
                logger.error(f"{log_prefix} Lỗi lấy thông tin reporter {reporter_user_id}: {e_get_reporter}")

        logger.info(f"{log_prefix} Đã đánh dấu báo cáo {report_id} là resolved.")
        return {'reporter_telegram_id': reporter_telegram_id}

    except Exception as e:
        logger.exception(f"{log_prefix} Lỗi không mong muốn khi giải quyết báo cáo: {e}")
        if isinstance(e, (DatabaseError, ValidationError)):
            raise e
        raise DatabaseError("Lỗi không mong muốn khi giải quyết báo cáo.", original_exception=e)