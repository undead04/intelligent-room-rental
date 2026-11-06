"""
Homigo Crawler & ETL Cron Job Scheduler
=======================================
Hệ thống lập lịch tự động chuẩn Python-Native (Zero-dependency ngoài thư viện chuẩn).
Tự động kích hoạt:
  1. Daily Crawl Job: Quét tin mới nhất hàng ngày và chạy pipeline ETL hoàn chỉnh (LLM, ML, pgvector).
  2. Weekly Verify Job: Quét tin cũ hàng tuần để kiểm tra tính khả dụng và cập nhật vòng đời bài đăng.

Đặc tính:
  - Non-overlapping Lock: Tránh chạy chồng chéo job khi phiên trước chưa kết thúc.
  - Graceful Shutdown: Bắt tín hiệu Ctrl+C / SIGINT / SIGTERM an toàn trên Windows/Linux.
  - CLI Runner: Cho phép kích hoạt tức thì bằng cờ `--run-now` phục vụ demo hội đồng.
"""

import os
import sys
import time
import signal
import logging
import argparse
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Any, Dict, List, Optional

# Đảm bảo ROOT_DIR nằm trong sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Điều chỉnh UTF-8 console output cho Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from crawler.config.settings import (
    SCHEDULER_DAILY_CRAWL_TIME,
    SCHEDULER_WEEKLY_VERIFY_DAY,
    SCHEDULER_WEEKLY_VERIFY_TIME,
    SCHEDULER_DAILY_PAGES,
    SCHEDULER_VERIFY_LIMIT,
    SCHEDULER_DEFAULT_REGION,
    SCHEDULER_DEFAULT_SOURCE,
)
from crawler.main import run_crawl_job

# Thiết lập logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [Scheduler] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("HomigoScheduler")

WEEKDAY_MAP = {
    "mon": 0, "monday": 0,
    "tue": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}


class ScheduledJob:
    """
    Biểu diễn một tác vụ được lên lịch trong HomigoScheduler.
    """

    def __init__(
        self,
        name: str,
        job_type: str,
        schedule_type: str,
        time_str: str,
        func: Callable,
        day_of_week: Optional[str] = None,
        args: Optional[tuple] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.job_type = job_type.lower()  # 'daily', 'weekly', 'update', 'verify'
        self.schedule_type = schedule_type.lower()  # 'daily' hoặc 'weekly'
        self.time_str = time_str.strip()  # "HH:MM"
        self.day_of_week = day_of_week.strip().lower() if day_of_week else None
        self.func = func
        self.args = args or ()
        self.kwargs = kwargs or {}

        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.calculate_next_run()

    def parse_time(self) -> tuple[int, int]:
        """Tách giờ và phút từ time_str (HH:MM)."""
        parts = self.time_str.split(":")
        if len(parts) != 2:
            raise ValueError(f"Định dạng thời gian không hợp lệ: '{self.time_str}'. Yêu cầu 'HH:MM'.")
        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except ValueError:
            raise ValueError(f"Giờ hoặc phút không phải là số hợp lệ trong '{self.time_str}'.")
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"Giờ ({hour}) hoặc phút ({minute}) không nằm trong khoảng hợp lệ (0-23:0-59).")
        return hour, minute

    def calculate_next_run(self, base_time: Optional[datetime] = None) -> datetime:
        """
        Tính toán thời điểm chạy tiếp theo dựa trên base_time (mặc định là hiện tại).
        """
        now = base_time or datetime.now()
        hour, minute = self.parse_time()

        if self.schedule_type == "daily":
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            self.next_run = candidate
            return candidate

        elif self.schedule_type == "weekly":
            if not self.day_of_week or self.day_of_week not in WEEKDAY_MAP:
                raise ValueError(f"Ngày trong tuần không hợp lệ: '{self.day_of_week}'.")

            target_weekday = WEEKDAY_MAP[self.day_of_week]
            current_weekday = now.weekday()

            days_ahead = (target_weekday - current_weekday) % 7
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)

            if candidate <= now:
                candidate += timedelta(days=7)

            self.next_run = candidate
            return candidate

        else:
            raise ValueError(f"Kiểu lịch không hỗ trợ: '{self.schedule_type}'")

    def __repr__(self) -> str:
        next_str = self.next_run.strftime("%Y-%m-%d %H:%M:%S") if self.next_run else "Chưa xác định"
        return f"<ScheduledJob name='{self.name}' type='{self.schedule_type}' next='{next_str}'>"


class HomigoScheduler:
    """
    Lõi lập lịch daemon Python-Native cho Homigo Crawler.
    Quản lý danh sách job, non-overlapping lock và hỗ trợ ngắt an toàn (Graceful Shutdown).
    """

    def __init__(self):
        self.jobs: List[ScheduledJob] = []
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self._is_running = False

    @property
    def job_lock(self) -> threading.Lock:
        """Alias cho lock kiểm soát non-overlapping."""
        return self.lock

    def run_job_now(self, target: str) -> bool:
        """Alias cho run_now phục vụ kiểm thử và gọi trực tiếp."""
        return self.run_now(target)

    def add_daily_job(
        self,
        name: str,
        time_str: str,
        func: Callable,
        args: Optional[tuple] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        job_type: str = "daily",
    ) -> ScheduledJob:
        """Đăng ký job chạy hàng ngày."""
        job = ScheduledJob(
            name=name,
            job_type=job_type,
            schedule_type="daily",
            time_str=time_str,
            func=func,
            args=args,
            kwargs=kwargs,
        )
        self.jobs.append(job)
        return job

    def add_weekly_job(
        self,
        name: str,
        day_of_week: str,
        time_str: str,
        func: Callable,
        args: Optional[tuple] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        job_type: str = "weekly",
    ) -> ScheduledJob:
        """Đăng ký job chạy hàng tuần vào một ngày cố định."""
        job = ScheduledJob(
            name=name,
            job_type=job_type,
            schedule_type="weekly",
            day_of_week=day_of_week,
            time_str=time_str,
            func=func,
            args=args,
            kwargs=kwargs,
        )
        self.jobs.append(job)
        return job

    def setup_default_jobs(
        self,
        pages: Optional[int] = None,
        limit: Optional[int] = None,
        region: Optional[str] = None,
        source: Optional[str] = None,
        no_clean: bool = False,
    ) -> None:
        """
        Đăng ký cấu hình mặc định:
          1. daily_crawl: 02:00 AM mỗi ngày (update + full ETL).
          2. weekly_verify: 04:00 AM Chủ Nhật mỗi tuần (verify status).
        """
        daily_pages = pages if pages is not None else SCHEDULER_DAILY_PAGES
        verify_limit = limit if limit is not None else SCHEDULER_VERIFY_LIMIT
        target_region = region or SCHEDULER_DEFAULT_REGION
        target_source = source or SCHEDULER_DEFAULT_SOURCE

        # 1. Daily Ingestion Job
        self.add_daily_job(
            name="daily_crawl",
            time_str=SCHEDULER_DAILY_CRAWL_TIME,
            func=run_crawl_job,
            kwargs={
                "pages": daily_pages,
                "region": target_region,
                "mode": "update",
                "full": not no_clean,
                "no_clean": no_clean,
                "limit": verify_limit,
                "source": target_source,
            },
            job_type="daily",
        )

        # 2. Weekly Verification Job
        self.add_weekly_job(
            name="weekly_verify",
            day_of_week=SCHEDULER_WEEKLY_VERIFY_DAY,
            time_str=SCHEDULER_WEEKLY_VERIFY_TIME,
            func=run_crawl_job,
            kwargs={
                "pages": daily_pages,
                "region": target_region,
                "mode": "verify",
                "full": False,
                "no_clean": True,
                "limit": verify_limit,
                "source": target_source,
            },
            job_type="weekly",
        )

    def execute_job(self, job: ScheduledJob) -> bool:
        """
        Thực thi một job với non-overlapping lock.
        Nếu một job khác đang chạy, lần thực thi này sẽ bị bỏ qua an toàn.
        """
        acquired = self.lock.acquire(blocking=False)
        if not acquired:
            logger.warning(
                f"⚠️ [Scheduler] Bỏ qua job '{job.name}' do có một tác vụ khác đang chạy dở (Non-overlapping Lock)."
            )
            return False

        try:
            logger.info(f"🚀 [Scheduler] BẮT ĐẦU THỰC THI JOB: '{job.name}' (Type: {job.job_type})...")
            start_time = time.time()
            job.func(*job.args, **job.kwargs)
            duration = time.time() - start_time

            job.last_run = datetime.now()
            job.calculate_next_run()
            logger.info(
                f"✅ [Scheduler] Job '{job.name}' HOÀN TẤT trong {duration:.2f}s. "
                f"Lần chạy kế tiếp: {job.next_run.strftime('%Y-%m-%d %H:%M:%S') if job.next_run else 'None'}"
            )
            return True
        except Exception as e:
            logger.error(f"❌ [Scheduler] Lỗi nghiêm trọng khi thực thi job '{job.name}': {e}", exc_info=True)
            job.last_run = datetime.now()
            job.calculate_next_run()
            return False
        finally:
            self.lock.release()

    def run_pending(self, now: Optional[datetime] = None) -> List[str]:
        """
        Kiểm tra và kích hoạt tất cả các job đã đến giờ chạy.
        Trả về danh sách tên các job được kích hoạt.
        """
        current_time = now or datetime.now()
        executed_jobs = []

        for job in self.jobs:
            if job.next_run and current_time >= job.next_run:
                executed = self.execute_job(job)
                if executed:
                    executed_jobs.append(job.name)

        return executed_jobs

    def run_now(self, target: str) -> bool:
        """
        Kích hoạt chạy ngay lập tức một job theo tên hoặc loại (demo mode).
        Hỗ trợ: 'daily', 'update', 'weekly', 'verify', hoặc tên cụ thể của job.
        """
        target_clean = target.strip().lower()
        matched_job = None

        for job in self.jobs:
            if (
                job.name.lower() == target_clean
                or job.job_type == target_clean
                or (target_clean == "update" and job.job_type == "daily")
                or (target_clean == "verify" and job.job_type == "weekly")
            ):
                matched_job = job
                break

        if not matched_job:
            available = [f"{j.name} (type: {j.job_type})" for j in self.jobs]
            logger.error(
                f"❌ Không tìm thấy job phù hợp với từ khóa '{target}'. Các job hiện có: {available}"
            )
            return False

        logger.info(f"🎯 [Scheduler] Kích hoạt chạy ngay tức thì (--run-now): '{matched_job.name}'...")
        return self.execute_job(matched_job)

    def print_schedule_summary(self) -> None:
        """In thông tin trực quan về các job đã được lên lịch."""
        print("\n" + "=" * 75)
        print("🕒 HOMIGO CRAWLER & ETL CRON JOB SCHEDULER (DAEMON)")
        print("=" * 75)
        print(f"{'TÊN JOB':<18} | {'CHU KỲ':<14} | {'THỜI GIAN':<10} | {'LẦN CHẠY KẾ TIẾP':<20}")
        print("-" * 75)

        for job in self.jobs:
            cycle = f"Thứ ({job.day_of_week})" if job.schedule_type == "weekly" else "Hàng ngày"
            next_str = job.next_run.strftime("%Y-%m-%d %H:%M:%S") if job.next_run else "N/A"
            print(f"{job.name:<18} | {cycle:<14} | {job.time_str:<10} | {next_str:<20}")

        print("=" * 75)
        print("💡 Gợi ý: Nhấn Ctrl+C để dừng an toàn (Graceful Shutdown).\n", flush=True)

    def register_signal_handlers(self) -> None:
        """Đăng ký bắt tín hiệu dừng hệ điều hành (SIGINT, SIGTERM)."""
        def _handler(signum, frame):
            sig_name = "SIGINT (Ctrl+C)" if signum == signal.SIGINT else f"Signal {signum}"
            logger.info(f"\n🛑 [Scheduler] Nhận tín hiệu ngắt {sig_name}. Đang yêu cầu dừng graceful...")
            self.stop()

        try:
            signal.signal(signal.SIGINT, _handler)
            if hasattr(signal, "SIGTERM"):
                signal.signal(signal.SIGTERM, _handler)
        except (ValueError, AttributeError):
            # Trong môi trường thread phụ hoặc test, signal có thể không đăng ký được
            pass

    def start(self, poll_interval: float = 1.0) -> None:
        """
        Khởi chạy vòng lặp scheduler chính (Daemon Loop).
        """
        self.register_signal_handlers()
        self.stop_event.clear()
        self._is_running = True

        self.print_schedule_summary()
        logger.info(f"🟢 Scheduler daemon đang hoạt động (Chu kỳ thăm dò: {poll_interval}s)...")

        try:
            while not self.stop_event.is_set():
                self.run_pending()
                self.stop_event.wait(poll_interval)
        except KeyboardInterrupt:
            logger.info("🛑 [Scheduler] Bắt được KeyboardInterrupt từ console.")
            self.stop()
        finally:
            self._is_running = False
            logger.info("👋 [Scheduler] Đã dừng hoàn toàn tiến trình scheduler an toàn.")

    def stop(self) -> None:
        """Dừng scheduler một cách an toàn."""
        self.stop_event.set()


def parse_args(args: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(
        description="Homigo Crawler Cron Job Scheduler - Lập lịch tự động cào và cập nhật dữ liệu phòng trọ"
    )
    parser.add_argument(
        "--run-now",
        type=str,
        choices=["daily", "update", "verify", "weekly"],
        help="Kích hoạt chạy ngay một job để demo mà không cần chờ lịch hẹn (hỗ trợ: daily, update, verify, weekly).",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=None,
        help=f"Ghi đè số trang cào hàng ngày (mặc định cấu hình: {SCHEDULER_DAILY_PAGES} trang).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=f"Ghi đè số tin kiểm tra định kỳ (mặc định cấu hình: {SCHEDULER_VERIFY_LIMIT} tin).",
    )
    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help=f"Khu vực cào (mặc định cấu hình: '{SCHEDULER_DEFAULT_REGION}').",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        choices=["nhatot", "phongtro123", "all"],
        help=f"Nguồn dữ liệu cào (mặc định cấu hình: '{SCHEDULER_DEFAULT_SOURCE}').",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Tắt ETL sau khi cào (chỉ lưu dữ liệu thô vào staging.db).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="Khoảng thời gian (giây) giữa các lần kiểm tra lịch hẹn (mặc định: 1.0s).",
    )
    return parser.parse_args(args)


def main(cli_args: Optional[List[str]] = None):
    args = parse_args(cli_args)

    scheduler = HomigoScheduler()
    scheduler.setup_default_jobs(
        pages=args.pages,
        limit=args.limit,
        region=args.region,
        source=args.source,
        no_clean=args.no_clean,
    )

    if args.run_now:
        # Chế độ chạy ngay (Demo mode)
        success = scheduler.run_now(args.run_now)
        sys.exit(0 if success else 1)
    else:
        # Chế độ Daemon lập lịch bình thường
        scheduler.start(poll_interval=args.poll_interval)


if __name__ == "__main__":
    main()
