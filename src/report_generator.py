"""报告邮件发送（报告内容由 report_helpers 基于用户数据集生成）。"""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_report_email(report_html: str, to_email: str, subject: str):
    """发送报告邮件"""
    try:
        from_addr = "reports@game-analyzer.com"
        msg = MIMEMultipart()
        msg['From'] = from_addr
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(report_html, 'html', 'utf-8'))

        return {"success": True, "message": "邮件发送成功（模拟）"}
    except Exception as e:
        return {"success": False, "message": "邮件发送失败: " + str(e)}

