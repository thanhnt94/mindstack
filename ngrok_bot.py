import logging
import asyncio # Vẫn cần cho asyncio.sleep và chạy async setup
import requests
import json
import subprocess
import sys
import os
# signal không cần thiết trực tiếp cho run_polling, nhưng có thể hữu ích cho systemd.
# Để đơn giản, tôi sẽ bỏ qua nó trong phiên bản này nếu không có yêu cầu cụ thể.

from telegram import Update, BotCommand
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# --- Cấu hình Bot và Ngrok ---
# Token Telegram Bot của bạn.
# Vui lòng thay thế bằng token thực tế của bot.
BOT_TOKEN = "7944284870:AAHiFhtedH93V56UPmPezhmE-zBnDqwdHYA" 

# Danh sách các Telegram User ID được phép sử dụng các lệnh quản trị (ví dụ: /restartngrok).
# Vui lòng thay thế bằng Telegram ID của bạn hoặc các admin ID khác.
# Nếu danh sách này trống, không ai có thể sử dụng các lệnh quản trị.
ALLOWED_TELEGRAM_IDS = [936620007] 

# Cấu hình URL API cục bộ của Ngrok. Ngrok thường chạy API trên cổng 4040 của localhost.
NGROK_API_URL = "http://127.0.0.1:4040/api/tunnels"
# Tên dịch vụ Ngrok trong systemd (giả định bạn đã cấu hình hoặc sẽ cấu hình).
# Đảm bảo tên này khớp với tên file .service của Ngrok (ví dụ: ngrok.service).
NGROK_SERVICE_NAME = "ngrok.service" 
# Địa chỉ IP và cổng mà ứng dụng web của bạn đang lắng nghe trên mạng nội bộ.
# Đảm bảo đây là IP và cổng mà Ngrok đang forward đến (ví dụ: 192.168.1.123:5000).
LOCAL_WEB_APP_ADDRESS = "192.168.1.123:5000" 

# --- Cấu hình Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s - %(name)s - %(funcName)s | (%(lineno)d) - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- Hàm giao tiếp với Ngrok (ĐỒNG BỘ) ---
def get_ngrok_public_url():
    """
    Mô tả: Lấy đường dẫn công khai (public URL) của Ngrok từ API cục bộ.
    Hàm này kết nối tới API của Ngrok đang chạy trên cùng máy chủ để lấy thông tin
    về các đường hầm đang hoạt động và trả về đường dẫn HTTPS.
    Args:
        Không có.
    Returns:
        str: Đường dẫn HTTPS công khai của Ngrok nếu tìm thấy, ngược lại trả về None.
    """
    try:
        response = requests.get(NGROK_API_URL, timeout=5)
        response.raise_for_status()  # Ném lỗi nếu phản hồi không thành công (4xx hoặc 5xx)
        
        tunnels_data = response.json()
        
        for tunnel in tunnels_data.get("tunnels", []):
            # Tìm đường hầm HTTPS và đảm bảo nó forward đến đúng địa chỉ cục bộ
            if tunnel.get("proto") == "https" and LOCAL_WEB_APP_ADDRESS in tunnel.get("config", {}).get("addr", ""):
                public_url = tunnel.get("public_url")
                logger.info(f"Đã tìm thấy đường dẫn Ngrok: {public_url}")
                return public_url
        
        logger.warning(f"Không tìm thấy đường hầm HTTPS đang hoạt động hoặc không forward đến {LOCAL_WEB_APP_ADDRESS}.")
        return None
        
    except requests.exceptions.ConnectionError:
        logger.error(f"Lỗi kết nối: Đảm bảo Ngrok đang chạy và API có thể truy cập tại {NGROK_API_URL}")
        return None
    except requests.exceptions.Timeout:
        logger.error(f"Lỗi thời gian chờ: Yêu cầu đến Ngrok API quá lâu.")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Lỗi khi yêu cầu Ngrok API: {e}")
        return None
    except json.JSONDecodeError:
        logger.error(f"Lỗi phân tích JSON từ phản hồi Ngrok API.")
        return None
    except Exception as e:
        logger.error(f"Một lỗi không mong muốn đã xảy ra khi lấy đường dẫn Ngrok: {e}", exc_info=True)
        return None

def restart_ngrok_service():
    """
    Mô tả: Khởi động lại dịch vụ Ngrok thông qua systemd.
    Hàm này thực thi lệnh hệ thống để khởi động lại dịch vụ Ngrok.
    Để hàm này hoạt động mà không cần mật khẩu sudo, bạn cần cấu hình
    file sudoers trên hệ thống Armbian của mình.
    Args:
        Không có.
    Returns:
        bool: True nếu dịch vụ được khởi động lại thành công, ngược lại False.
    """
    logger.info(f"Đang cố gắng khởi động lại dịch vụ Ngrok ({NGROK_SERVICE_NAME})...")
    try:
        command = ["sudo", "systemctl", "restart", NGROK_SERVICE_NAME]
        
        # Chạy lệnh và chờ nó hoàn thành
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        
        logger.info(f"Dịch vụ Ngrok đã được khởi động lại thành công.")
        logger.debug(f"Stdout: {result.stdout}")
        logger.debug(f"Stderr: {result.stderr}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Lỗi khi thực thi lệnh khởi động lại dịch vụ Ngrok:")
        logger.error(f"Lệnh: {' '.join(e.cmd)}")
        logger.error(f"Mã thoát: {e.returncode}")
        logger.error(f"Stdout: {e.stdout}")
        logger.error(f"Stderr: {e.stderr}")
        logger.error("Vui lòng kiểm tra xem dịch vụ Ngrok có tồn tại và người dùng hiện tại có quyền sudo để khởi động lại mà không cần mật khẩu hay không.")
        return False
    except FileNotFoundError:
        logger.error("Lỗi: Lệnh 'sudo' hoặc 'systemctl' không tìm thấy. Đảm bảo chúng đã được cài đặt và nằm trong PATH.")
        return False
    except Exception as e:
        logger.error(f"Một lỗi không mong muốn đã xảy ra khi khởi động lại dịch vụ Ngrok: {e}", exc_info=True)
        return False

# --- Handlers cho Telegram Bot (BẤT ĐỒNG BỘ) ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Mô tả: Handler cho lệnh /start.
    Gửi tin nhắn chào mừng và hướng dẫn sử dụng.
    Args:
        update (Update): Đối tượng cập nhật từ Telegram.
        context (ContextTypes.DEFAULT_TYPE): Đối tượng ngữ cảnh.
    Returns:
        None
    """
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    logger.info(f"Người dùng {user_id} ({user_name}) đã gửi lệnh /start.")
    await update.message.reply_text(
        f"Chào mừng bạn, {user_name}!\n"
        "Tôi là bot quản lý Ngrok của bạn.\n"
        "Sử dụng các lệnh sau:\n"
        "/getngrokurl - Lấy đường dẫn Ngrok hiện tại\n"
        "/restartngrok - Khởi động lại dịch vụ Ngrok (chỉ admin)"
    )
    logger.info(f"Đã phản hồi lệnh /start cho người dùng {user_id}.")

async def get_ngrok_url_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Mô tả: Handler cho lệnh /getngrokurl.
    Lấy đường dẫn công khai của Ngrok và gửi về cho người dùng.
    Lệnh này có thể được sử dụng bởi BẤT KỲ AI.
    Args:
        update (Update): Đối tượng cập nhật từ Telegram.
        context (ContextTypes.DEFAULT_TYPE): Đối tượng ngữ cảnh.
    Returns:
        None
    """
    user_id = update.effective_user.id 
    logger.info(f"Người dùng {user_id} đã gửi lệnh /getngrokurl.")
    await update.message.reply_text("Đang lấy đường dẫn Ngrok hiện tại, vui lòng chờ...")

    ngrok_url = get_ngrok_public_url() # Gọi hàm đồng bộ

    if ngrok_url:
        await update.message.reply_text(f"Đường dẫn Ngrok hiện tại của bạn là:\n`{ngrok_url}`", parse_mode='MarkdownV2')
        logger.info(f"Đã gửi đường dẫn Ngrok cho người dùng {user_id}: {ngrok_url}")
    else:
        await update.message.reply_text("Không thể lấy đường dẫn Ngrok. Vui lòng đảm bảo Ngrok đang chạy và API của nó khả dụng.")
        logger.warning(f"Không thể lấy đường dẫn Ngrok cho người dùng {user_id}.")

async def restart_ngrok_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Mô tả: Handler cho lệnh /restartngrok.
    Khởi động lại dịch vụ Ngrok.
    Chỉ cho phép các Telegram ID được cấu hình trong ALLOWED_TELEGRAM_IDS sử dụng.
    Args:
        update (Update): Đối tượng cập nhật từ Telegram.
        context (ContextTypes.DEFAULT_TYPE): Đối tượng ngữ cảnh.
    Returns:
        None
    """
    user_id = update.effective_user.id
    logger.info(f"Người dùng {user_id} đã gửi lệnh /restartngrok.")
    if user_id not in ALLOWED_TELEGRAM_IDS:
        await update.message.reply_text("Bạn không có quyền sử dụng lệnh này.")
        logger.warning(f"Người dùng không được phép (ID: {user_id}) đã cố gắng sử dụng /restartngrok.")
        return

    logger.info(f"Người dùng {user_id} đã yêu cầu /restartngrok.")
    await update.message.reply_text("Đang cố gắng khởi động lại dịch vụ Ngrok, vui lòng chờ...")

    success = restart_ngrok_service() # Gọi hàm đồng bộ

    if success:
        await asyncio.sleep(5) # Vẫn cần await cho sleep
        new_ngrok_url = get_ngrok_public_url()
        if new_ngrok_url:
            await update.message.reply_text(f"Dịch vụ Ngrok đã được khởi động lại thành công.\nĐường dẫn mới là:\n`{new_ngrok_url}`", parse_mode='MarkdownV2')
            logger.info(f"Dịch vụ Ngrok đã khởi động lại và gửi đường dẫn mới cho người dùng {user_id}: {new_ngrok_url}")
        else:
            await update.message.reply_text("Dịch vụ Ngrok đã khởi động lại, nhưng không thể lấy được đường dẫn mới.")
            logger.warning(f"Dịch vụ Ngrok khởi động lại nhưng không lấy được link mới cho người dùng {user_id}.")
    else:
        await update.message.reply_text("Không thể khởi động lại dịch vụ Ngrok. Vui lòng kiểm tra log bot để biết chi tiết.")
        logger.error(f"Không thể khởi động lại dịch vụ Ngrok cho người dùng {user_id}.")

async def generic_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Mô tả: Handler chung để ghi log mọi tin nhắn không phải lệnh.
    Args:
        update (Update): Đối tượng cập nhật từ Telegram.
        context (ContextTypes.DEFAULT_TYPE): Đối tượng ngữ cảnh.
    Returns:
        None
    """
    if update.message and update.message.text:
        logger.info(f"Người dùng {update.effective_user.id} đã gửi tin nhắn: '{update.message.text}'")
    elif update.message:
        logger.info(f"Người dùng {update.effective_user.id} đã gửi tin nhắn không phải văn bản.")

async def set_bot_commands(application: Application):
    """
    Mô tả: Thiết lập danh sách lệnh gợi ý hiển thị trên Telegram.
    Args:
        application (Application): Đối tượng ứng dụng Telegram bot.
    Returns:
        None
    """
    logger.info("⏳ Đang thiết lập danh sách lệnh bot...")
    commands = [
        BotCommand("start", "Khởi động bot và xem hướng dẫn"),
        BotCommand("getngrokurl", "Lấy đường dẫn Ngrok hiện tại"),
        BotCommand("restartngrok", "Khởi động lại dịch vụ Ngrok"),
    ]
    try:
        await application.bot.set_my_commands(commands)
        logger.info(f"✅ Lệnh bot đã được thiết lập thành công ({len(commands)} lệnh).")
    except Exception as e:
        logger.error(f"❌ Lỗi khi thiết lập lệnh bot: {e}", exc_info=True)

def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        logger.critical("LỖI NGHIÊM TRỌNG: BOT_TOKEN chưa được thiết lập. Vui lòng thay thế placeholder.")
        sys.exit(1)

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("getngrokurl", get_ngrok_url_command))
    application.add_handler(CommandHandler("restartngrok", restart_ngrok_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generic_message_handler))
    application.add_handler(MessageHandler(filters.ALL & ~filters.TEXT & ~filters.COMMAND, generic_message_handler))

    logger.info(">>> Ngrok Management Bot đang chạy...")

    # Không cần setup_command nếu chưa cần fancy
    application.run_polling()


if __name__ == "__main__":
    # Khối khởi chạy chính. Gọi hàm main() đồng bộ.
    try:
        main() 
    except KeyboardInterrupt:
        logger.info("Bot đã dừng bởi người dùng (Ctrl+C).")
    except Exception as e:
        logger.critical(f"Lỗi nghiêm trọng khi chạy bot: {e}", exc_info=True)

