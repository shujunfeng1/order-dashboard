"""
邮件读取模块
通过 IMAP 协议连接邮箱，搜索带附件的邮件，下载 Excel 附件。
支持中文主题搜索（UTF-8 编码）。
"""

import imaplib
import email
import os
from email.header import decode_header
from pathlib import Path
from datetime import datetime, date, timedelta


def decode_mime_header(header_value):
    """解码 MIME 编码的邮件头。"""
    if not header_value:
        return ""
    decoded_parts = decode_header(header_value)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def connect_mailbox(config):
    """连接 IMAP 邮箱。优先从环境变量读取凭据（GitHub Actions 用）。"""
    email_config = config["email"]
    server = os.environ.get("IMAP_SERVER", email_config["imap_server"])
    port = int(os.environ.get("IMAP_PORT", email_config["imap_port"]))
    account = os.environ.get("EMAIL_ACCOUNT", email_config["email_account"])
    password = os.environ.get("EMAIL_PASSWORD", email_config["email_password"])

    print(f"[邮件读取] 正在连接 {server}:{port} ...")
    mail = imaplib.IMAP4_SSL(server, port)
    # 设置 UTF-8 编码，支持中文搜索
    mail._encoding = "utf-8"
    mail.login(account, password)
    mail.select("INBOX")
    print(f"[邮件读取] 登录成功: {account}")
    return mail


def search_emails(mail, config):
    """搜索符合条件的邮件（今天的邮件 + 主题关键词）。"""
    email_config = config["email"]
    subject_filter = email_config.get("subject_filter", "")
    today = date.today().strftime("%d-%b-%Y")

    # 先搜索今天的邮件
    print(f"[邮件读取] 搜索日期: {today}, 主题关键词: {subject_filter}")
    status, message_ids = mail.search("UTF-8", "ON", today, "SUBJECT", f'"{subject_filter}"')

    if status != "OK":
        print("[邮件读取] 搜索失败")
        return []

    id_list = message_ids[0].split()
    print(f"[邮件读取] 今天找到 {len(id_list)} 封匹配邮件")

    # 如果今天没找到，尝试搜索昨天的（兜底：可能刚过午夜）
    if not id_list:
        yesterday = (date.today() - timedelta(days=1)).strftime("%d-%b-%Y")
        print(f"[邮件读取] 今天未找到，尝试搜索昨天: {yesterday}")
        status, message_ids = mail.search("UTF-8", "ON", yesterday, "SUBJECT", f'"{subject_filter}"')
        if status == "OK":
            id_list = message_ids[0].split()
            print(f"[邮件读取] 昨天找到 {len(id_list)} 封匹配邮件")

    # 如果还没找到，搜索最近3天的（再兜底）
    if not id_list:
        print("[邮件读取] 今天和昨天均未找到，搜索最近所有匹配邮件...")
        status, message_ids = mail.search("UTF-8", "SUBJECT", f'"{subject_filter}"')
        if status == "OK":
            all_ids = message_ids[0].split()
            # 取最近5封
            id_list = all_ids[-5:] if len(all_ids) >= 5 else all_ids
            print(f"[邮件读取] 共 {len(all_ids)} 封历史邮件，取最近 {len(id_list)} 封")

    return id_list


def search_latest_email(mail, config):
    """搜索最新的一封匹配邮件（不限日期），用于兜底获取最新数据。"""
    email_config = config["email"]
    subject_filter = email_config.get("subject_filter", "")

    status, message_ids = mail.search("UTF-8", "SUBJECT", f'"{subject_filter}"')
    if status == "OK" and message_ids[0]:
        all_ids = message_ids[0].split()
        if all_ids:
            return [all_ids[-1]]  # 返回最新的一封
    return []


def download_attachments(mail, message_ids, config, output_dir):
    """下载邮件附件。"""
    email_config = config["email"]
    attachment_keyword = email_config.get("attachment_keyword", ".xlsx")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded_files = []

    for msg_id in message_ids:
        print(f"[邮件读取] 获取邮件 {msg_id.decode()}...")
        status, msg_data = mail.fetch(msg_id, "(RFC822)")
        if status != "OK":
            continue

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = decode_mime_header(msg.get("Subject", ""))
        sender = decode_mime_header(msg.get("From", ""))
        date_str = msg.get("Date", "")
        print(f"  主题: {subject}")
        print(f"  发件人: {sender}")
        print(f"  日期: {date_str}")

        # 遍历邮件部分，查找附件
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" not in content_disposition:
                continue

            filename = part.get_filename()
            if filename:
                filename = decode_mime_header(filename)

            if not filename or attachment_keyword not in filename.lower():
                continue

            # 下载附件
            filepath = output_dir / filename
            payload = part.get_payload(decode=True)
            if payload:
                with open(filepath, "wb") as f:
                    f.write(payload)
                print(f"  附件已下载: {filepath} ({len(payload)} bytes)")
                downloaded_files.append(str(filepath))

    return downloaded_files


def fetch_and_download(config, output_dir=None):
    """
    完整流程：连接邮箱 → 搜索邮件 → 下载附件。

    Args:
        config: 配置字典
        output_dir: 附件保存目录

    Returns:
        list: 下载的文件路径列表
    """
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "attachments"

    try:
        mail = connect_mailbox(config)

        # 先搜索今天的邮件
        message_ids = search_emails(mail, config)

        if not message_ids:
            print("[邮件读取] 未找到匹配邮件")
            mail.logout()
            return []

        files = download_attachments(mail, message_ids, config, output_dir)
        mail.logout()

        if files:
            # 只返回最新的一个文件
            latest = max(files, key=lambda f: Path(f).stat().st_mtime)
            print(f"[邮件读取] 最新附件: {latest}")
            return [latest]

        return files
    except Exception as e:
        print(f"[邮件读取] 错误: {e}")
        import traceback
        traceback.print_exc()
        return []


if __name__ == "__main__":
    import json
    import sys

    config_path = Path(__file__).parent.parent / "config" / "settings.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    if not config["email"]["email_account"]:
        print("请先在 config/settings.json 中配置邮箱信息")
        print("需要填写: imap_server, email_account, email_password")
        sys.exit(1)

    output = sys.argv[1] if len(sys.argv) > 1 else None
    files = fetch_and_download(config, output)
    if files:
        print(f"\n下载完成: {files}")
    else:
        print("\n没有下载到附件")
