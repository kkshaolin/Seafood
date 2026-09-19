import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOG_DIR = Path(os.environ.get("LOG_DIR", str(WORKSPACE_ROOT / "storage" / "logs")))
if not DEFAULT_LOG_DIR.exists() and os.environ.get("LOG_DIR") is None:
    # Fallback to /app/logs if inside Docker
    if Path("/app/logs").exists() or Path("/app").exists():
        DEFAULT_LOG_DIR = Path("/app/logs")


class CustomLogger:
    """
    Custom Logger ที่รองรับหลักการพื้นฐานของการทำ Log
    
    หลักการออกแบบ:
    1. Multiple Logger Management - จัดการ Logger แต่ละโมดูลอย่างเป็นสัดส่วน
    2. Absolute Path Storage - บันทึกไฟล์ลง storage/logs เสมอไม่ว่าจะสั่งรันจากโฟลเดอร์ใด
    3. Log Rotation - ป้องกันไฟล์ใหญ่เกินไป (ตัดไฟล์ที่ 5MB เก็บสำรอง 3 ไฟล์)
    4. Structured Format - รูปแบบชัดเจน อ่านง่าย พร้อมบอกชื่อไฟล์และบรรทัด
    5. Configurable Levels - ตั้งค่าระดับ Log ได้ตามต้องการ
    """
    
    _loggers = {}
    
    @classmethod
    def get_logger(
        cls,
        name: str = "ProjectLogger",
        log_dir: Path | str = DEFAULT_LOG_DIR,
        log_level: int = logging.DEBUG,
        max_bytes: int = 5 * 1024 * 1024,  # 5MB
        backup_count: int = 3,
    ) -> logging.Logger:
        """
        ดึงหรือสร้าง Logger ตามชื่อโมดูล โดยการันตีบันทึกไฟล์ลง storage/logs/
        """
        if name in cls._loggers:
            return cls._loggers[name]

        # ใช้ storage/logs ที่อยู่ที่ root ของ workspace เท่านั้น
        target_dir = Path(log_dir)
        if not target_dir.is_absolute():
            target_dir = DEFAULT_LOG_DIR
        target_dir = target_dir.resolve()

        # สร้างโฟลเดอร์ถ้ายังไม่มี
        os.makedirs(target_dir, exist_ok=True)

        logger = logging.getLogger(name)
        logger.setLevel(log_level)
        logger.propagate = False  # ป้องกัน Duplicate Logs ใน Parent Loggers

        # ดึง Trace ID และ Span ID จาก OpenTelemetry มาแนบใน Log อัตโนมัติเพื่อทำ Log Correlation
        class TraceContextFilter(logging.Filter):
            def filter(self, record):
                try:
                    from opentelemetry import trace
                    ctx = trace.get_current_span().get_span_context()
                    if ctx.is_valid:
                        record.otelTraceID = trace.format_trace_id(ctx.trace_id)
                        record.otelSpanID = trace.format_span_id(ctx.span_id)
                    else:
                        record.otelTraceID = "0"
                        record.otelSpanID = "0"
                except ImportError:
                    record.otelTraceID = "0"
                    record.otelSpanID = "0"
                except Exception as e:
                    # กำหนดค่า 0 หากเกิดข้อผิดพลาด พร้อมพิมพ์ Error ลง stderr เพื่อไม่ให้บั๊กถูกซ่อน
                    record.otelTraceID = "0"
                    record.otelSpanID = "0"
                    import sys
                    print(f"Warning: TraceContextFilter encountered an unexpected error: {e}", file=sys.stderr)
                return True
                
        logger.addFilter(TraceContextFilter())

        # ป้องกันการเพิ่ม Handler ซ้ำ
        if not logger.handlers:
            class SafeOtelFormatter(logging.Formatter):
                def format(self, record):
                    if not hasattr(record, 'otelTraceID'):
                        record.otelTraceID = "-"
                    if not hasattr(record, 'otelSpanID'):
                        record.otelSpanID = "-"
                    return super().format(record)

            formatter = SafeOtelFormatter(
                fmt="%(asctime)s | %(levelname)-8s | trace_id=%(otelTraceID)s span_id=%(otelSpanID)s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

            # === Handler 1: Console Handler (แสดงผลบนหน้าจอ) ===
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

            # === Handler 2: General File Handler (บันทึกทุก Level ลง storage/logs/app.log) ===
            general_log_file = target_dir / "app.log"
            file_handler = RotatingFileHandler(
                general_log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            # === Handler 3: Module Specific File Handler (บันทึกลง storage/logs/{name}.log) ===
            module_log_file = target_dir / f"{name.lower()}.log"
            module_handler = RotatingFileHandler(
                module_log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            module_handler.setLevel(logging.DEBUG)
            module_handler.setFormatter(formatter)
            logger.addHandler(module_handler)

            # === Handler 4: Error File Handler (แยกบันทึกเฉพาะ ERROR & CRITICAL) ===
            error_log_file = target_dir / "app_error.log"
            error_handler = RotatingFileHandler(
                error_log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(formatter)
            logger.addHandler(error_handler)

        cls._loggers[name] = logger
        return logger


def get_logger(name: str = "ProjectLogger") -> logging.Logger:
    """
    ฟังก์ชัน Helper สำหรับดึง Logger ไปใช้งานในทุกโมดูล
    
    Usage:
        logger = get_logger("auth_service")
        logger.info("User logged in")
    """
    return CustomLogger.get_logger(name=name)


if __name__ == "__main__":
    test_logger = get_logger("test_module")
    test_logger.debug("This is DEBUG log - saved to storage/logs")
    test_logger.info("This is INFO log - saved to storage/logs")
    test_logger.warning("This is WARNING log - saved to storage/logs")
    test_logger.error("This is ERROR log - saved to storage/logs/app_error.log")
    test_logger.critical("This is CRITICAL log - saved to storage/logs/app_error.log")

    print("\n✅ Logger verified successfully!")
    print(f"📁 Log files are stored in: {DEFAULT_LOG_DIR.resolve()}")