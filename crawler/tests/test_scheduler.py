"""
Black-box Independent Test Suite cho Homigo Crawler Cron Job Scheduler
========================================================================
Kiểm thử toàn diện module crawler/scheduler.py theo chuẩn Black-box Testing:
- Nhóm 1: Happy Path (parse thời gian, tính next_run, setup default, run_pending, run_job_now)
- Nhóm 2: Boundary & Edge Cases (giờ/phút sai, thứ sai, callback crash, job không tồn tại)
- Nhóm 3: Concurrency & Race Condition (Non-overlapping Lock, Mutual Exclusion đa luồng)
- Nhóm 4: Integration & Graceful Shutdown (Stop daemon loop, CLI arguments, Main execution)
"""

import sys
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Đảm bảo import được module crawler
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from crawler.scheduler import ScheduledJob, HomigoScheduler, parse_args, main, WEEKDAY_MAP
from crawler.config.settings import (
    SCHEDULER_DAILY_CRAWL_TIME,
    SCHEDULER_WEEKLY_VERIFY_DAY,
    SCHEDULER_WEEKLY_VERIFY_TIME,
    SCHEDULER_DAILY_PAGES,
    SCHEDULER_VERIFY_LIMIT,
    SCHEDULER_DEFAULT_REGION,
    SCHEDULER_DEFAULT_SOURCE,
)


# ==============================================================================
# NHÓM 1 — HAPPY PATH
# ==============================================================================

class TestHappyPath:
    """Kiểm tra các luồng nghiệp vụ hoạt động lý tưởng và chính xác theo đặc tả."""

    @pytest.mark.parametrize(
        "time_str,expected_hour,expected_minute",
        [
            ("02:00", 2, 0),
            ("00:00", 0, 0),
            ("23:59", 23, 59),
            ("14:30", 14, 30),
            ("09:05", 9, 5),
        ],
    )
    def test_parse_time_valid(self, time_str, expected_hour, expected_minute):
        """Parse HH:MM chuẩn xác thành (hour, minute)."""
        job = ScheduledJob(
            name="test_parse",
            job_type="daily",
            schedule_type="daily",
            time_str=time_str,
            func=lambda: None,
        )
        hour, minute = job.parse_time()
        assert hour == expected_hour
        assert minute == expected_minute

    def test_calculate_next_run_daily_later_today(self):
        """Daily job với giờ hẹn muộn hơn thời điểm hiện tại -> chạy trong ngày hôm nay."""
        base_time = datetime(2026, 11, 6, 10, 0, 0)  # 10:00 sáng
        job = ScheduledJob(
            name="daily_test",
            job_type="daily",
            schedule_type="daily",
            time_str="14:00",
            func=lambda: None,
        )
        next_run = job.calculate_next_run(base_time=base_time)
        assert next_run == datetime(2026, 11, 6, 14, 0, 0)

    def test_calculate_next_run_daily_earlier_today(self):
        """Daily job với giờ hẹn sớm hơn thời điểm hiện tại -> chạy vào ngày mai."""
        base_time = datetime(2026, 11, 6, 10, 0, 0)  # 10:00 sáng
        job = ScheduledJob(
            name="daily_test",
            job_type="daily",
            schedule_type="daily",
            time_str="08:00",
            func=lambda: None,
        )
        next_run = job.calculate_next_run(base_time=base_time)
        assert next_run == datetime(2026, 11, 7, 8, 0, 0)

    def test_calculate_next_run_daily_exact_same_time(self):
        """Daily job trùng đúng thời điểm hiện tại -> dời sang ngày tiếp theo (candidate <= now)."""
        base_time = datetime(2026, 11, 6, 10, 0, 0)
        job = ScheduledJob(
            name="daily_test",
            job_type="daily",
            schedule_type="daily",
            time_str="10:00",
            func=lambda: None,
        )
        next_run = job.calculate_next_run(base_time=base_time)
        assert next_run == datetime(2026, 11, 7, 10, 0, 0)

    def test_calculate_next_run_weekly_upcoming_day(self):
        """Weekly job vào thứ sắp tới trong tuần (Thứ 6 -> Chủ nhật)."""
        base_time = datetime(2026, 11, 6, 10, 0, 0)  # Thứ Sáu
        job = ScheduledJob(
            name="weekly_test",
            job_type="weekly",
            schedule_type="weekly",
            day_of_week="sun",
            time_str="04:00",
            func=lambda: None,
        )
        next_run = job.calculate_next_run(base_time=base_time)
        assert next_run == datetime(2026, 11, 8, 4, 0, 0)  # Chủ Nhật 08/11/2026
        assert next_run.weekday() == 6

    def test_calculate_next_run_weekly_same_day_later(self):
        """Weekly job trùng thứ hôm nay nhưng giờ hẹn muộn hơn -> chạy trong ngày."""
        base_time = datetime(2026, 11, 6, 10, 0, 0)  # Thứ Sáu 10:00
        job = ScheduledJob(
            name="weekly_test",
            job_type="weekly",
            schedule_type="weekly",
            day_of_week="friday",
            time_str="15:30",
            func=lambda: None,
        )
        next_run = job.calculate_next_run(base_time=base_time)
        assert next_run == datetime(2026, 11, 6, 15, 30, 0)

    def test_calculate_next_run_weekly_same_day_earlier(self):
        """Weekly job trùng thứ hôm nay nhưng giờ hẹn đã qua -> dời sang tuần sau (+7 ngày)."""
        base_time = datetime(2026, 11, 6, 10, 0, 0)  # Thứ Sáu 10:00
        job = ScheduledJob(
            name="weekly_test",
            job_type="weekly",
            schedule_type="weekly",
            day_of_week="fri",
            time_str="08:00",
            func=lambda: None,
        )
        next_run = job.calculate_next_run(base_time=base_time)
        assert next_run == datetime(2026, 11, 13, 8, 0, 0)

    def test_calculate_next_run_weekly_passed_day(self):
        """Weekly job vào thứ đã qua trong tuần (Thứ Sáu -> Thứ Tư tuần sau)."""
        base_time = datetime(2026, 11, 6, 10, 0, 0)  # Thứ Sáu
        job = ScheduledJob(
            name="weekly_test",
            job_type="weekly",
            schedule_type="weekly",
            day_of_week="wed",
            time_str="09:00",
            func=lambda: None,
        )
        next_run = job.calculate_next_run(base_time=base_time)
        assert next_run == datetime(2026, 11, 11, 9, 0, 0)  # Thứ Tư tuần sau
        assert next_run.weekday() == 2

    def test_setup_default_jobs_registers_expected_tasks(self):
        """setup_default_jobs() đăng ký đầy đủ 2 job mặc định từ settings."""
        scheduler = HomigoScheduler()
        scheduler.setup_default_jobs()

        assert len(scheduler.jobs) == 2
        names = [j.name for j in scheduler.jobs]
        assert "daily_crawl" in names
        assert "weekly_verify" in names

        daily_job = next(j for j in scheduler.jobs if j.name == "daily_crawl")
        assert daily_job.schedule_type == "daily"
        assert daily_job.time_str == SCHEDULER_DAILY_CRAWL_TIME
        assert daily_job.kwargs["pages"] == SCHEDULER_DAILY_PAGES
        assert daily_job.kwargs["region"] == SCHEDULER_DEFAULT_REGION
        assert daily_job.kwargs["source"] == SCHEDULER_DEFAULT_SOURCE
        assert daily_job.kwargs["mode"] == "update"
        assert daily_job.kwargs["full"] is True
        assert daily_job.kwargs["no_clean"] is False

        weekly_job = next(j for j in scheduler.jobs if j.name == "weekly_verify")
        assert weekly_job.schedule_type == "weekly"
        assert weekly_job.day_of_week == SCHEDULER_WEEKLY_VERIFY_DAY
        assert weekly_job.time_str == SCHEDULER_WEEKLY_VERIFY_TIME
        assert weekly_job.kwargs["mode"] == "verify"
        assert weekly_job.kwargs["full"] is False
        assert weekly_job.kwargs["no_clean"] is True
        assert weekly_job.kwargs["limit"] == SCHEDULER_VERIFY_LIMIT

    def test_setup_default_jobs_parameter_overrides(self):
        """setup_default_jobs() áp dụng chính xác các tham số ghi đè CLI."""
        scheduler = HomigoScheduler()
        scheduler.setup_default_jobs(
            pages=5,
            limit=50,
            region="hcm",
            source="nhatot",
            no_clean=True,
        )

        daily_job = next(j for j in scheduler.jobs if j.name == "daily_crawl")
        assert daily_job.kwargs["pages"] == 5
        assert daily_job.kwargs["limit"] == 50
        assert daily_job.kwargs["region"] == "hcm"
        assert daily_job.kwargs["source"] == "nhatot"
        assert daily_job.kwargs["no_clean"] is True
        assert daily_job.kwargs["full"] is False

    def test_run_pending_triggers_due_jobs(self):
        """run_pending() kích hoạt đúng job khi next_run <= current_time."""
        scheduler = HomigoScheduler()
        mock_func = MagicMock()

        job = scheduler.add_daily_job("mock_job", "02:00", mock_func)
        # Giả lập thời điểm next_run đã tới
        job.next_run = datetime(2026, 11, 6, 2, 0, 0)
        current_time = datetime(2026, 11, 6, 2, 5, 0)  # Đã quá 5 phút

        executed = scheduler.run_pending(now=current_time)
        assert "mock_job" in executed
        assert mock_func.call_count == 1
        assert job.last_run is not None
        # next_run phải được cập nhật sang lần kế tiếp
        assert job.next_run > current_time

    def test_run_pending_does_not_trigger_future_jobs(self):
        """run_pending() không kích hoạt job khi chưa tới giờ (current_time < next_run)."""
        scheduler = HomigoScheduler()
        mock_func = MagicMock()

        job = scheduler.add_daily_job("mock_job", "14:00", mock_func)
        job.next_run = datetime(2026, 11, 6, 14, 0, 0)
        current_time = datetime(2026, 11, 6, 13, 59, 59)

        executed = scheduler.run_pending(now=current_time)
        assert len(executed) == 0
        mock_func.assert_not_called()

    def test_run_job_now_executes_target_immediately(self):
        """run_job_now() và run_now() kích hoạt thực thi trực tiếp job được chỉ định."""
        scheduler = HomigoScheduler()
        mock_daily = MagicMock()
        mock_weekly = MagicMock()

        scheduler.add_daily_job("daily_crawl", "02:00", mock_daily, kwargs={"mode": "daily"})
        scheduler.add_weekly_job("weekly_verify", "sun", "04:00", mock_weekly, kwargs={"mode": "weekly"})

        # Chạy daily theo tên
        res_daily = scheduler.run_job_now("daily_crawl")
        assert res_daily is True
        mock_daily.assert_called_once_with(mode="daily")
        mock_weekly.assert_not_called()

        # Chạy weekly theo bí danh type "verify"
        mock_daily.reset_mock()
        res_weekly = scheduler.run_now("verify")
        assert res_weekly is True
        mock_weekly.assert_called_once_with(mode="weekly")
        mock_daily.assert_not_called()


# ==============================================================================
# NHÓM 2 — BOUNDARY & EDGE CASES
# ==============================================================================

class TestBoundaryAndEdgeCases:
    """Kiểm tra phản ứng của Scheduler trước dữ liệu biên, dữ liệu dị thường và ngoại lệ."""

    @pytest.mark.parametrize(
        "invalid_time",
        [
            "25:00",     # Giờ quá 23
            "abc",       # Không có dấu hai chấm
            "",          # Chuỗi rỗng
            "12:99",     # Phút quá 59
            "12:abc",    # Phút không phải số
            "-1:30",     # Giờ âm
            "12:-05",    # Phút âm
            "12:30:45",  # Ba thành phần (HH:MM:SS)
            ":30",       # Thiếu giờ
            "12:",       # Thiếu phút
        ],
    )
    def test_parse_time_invalid_format(self, invalid_time):
        """Định dạng giờ/phút sai phải ném lỗi ValueError."""
        with pytest.raises(ValueError):
            ScheduledJob(
                name="err_job",
                job_type="daily",
                schedule_type="daily",
                time_str=invalid_time,
                func=lambda: None,
            )

    @pytest.mark.parametrize(
        "invalid_day",
        [
            "funday",
            "",
            "   ",
            "unknown",
            "123",
        ],
    )
    def test_weekly_invalid_day_of_week(self, invalid_day):
        """Tên thứ trong tuần sai phải ném lỗi ValueError."""
        with pytest.raises(ValueError):
            ScheduledJob(
                name="err_weekly",
                job_type="weekly",
                schedule_type="weekly",
                day_of_week=invalid_day,
                time_str="04:00",
                func=lambda: None,
            )

    def test_unsupported_schedule_type(self):
        """Loại lịch không hỗ trợ (ví dụ: monthly) phải ném ValueError."""
        with pytest.raises(ValueError, match="Kiểu lịch không hỗ trợ"):
            ScheduledJob(
                name="monthly_job",
                job_type="monthly",
                schedule_type="monthly",
                time_str="04:00",
                func=lambda: None,
            )

    def test_job_callback_exception_handled_gracefully(self):
        """Job callback bị bắn ngoại lệ: Scheduler phải bắt lỗi, trả về False và KHÔNG sập."""
        scheduler = HomigoScheduler()

        def failing_job():
            raise RuntimeError("Cố tình ném lỗi kết nối Staging DB để kiểm thử độ bền!")

        job = scheduler.add_daily_job("failing_job", "02:00", failing_job)
        job.next_run = datetime(2026, 11, 6, 2, 0, 0)

        # Thực thi qua run_pending
        executed = scheduler.run_pending(now=datetime(2026, 11, 6, 2, 1, 0))

        # Do job bị fail, executed list không chứa job này
        assert "failing_job" not in executed
        # Lock phải được giải phóng hoàn toàn sau khi fail
        assert not scheduler.lock.locked()
        # last_run và next_run vẫn được cập nhật để tránh lặp vô tận
        assert job.last_run is not None
        assert job.next_run > datetime(2026, 11, 6, 2, 1, 0)

    def test_run_job_now_unknown_target_returns_false(self):
        """Gọi run_job_now() hoặc run_now() với tên job không tồn tại: trả về False, không crash."""
        scheduler = HomigoScheduler()
        scheduler.setup_default_jobs()

        result = scheduler.run_job_now("unknown_job_xyz")
        assert result is False

        result_run_now = scheduler.run_now("ghost_job")
        assert result_run_now is False

    def test_run_pending_survives_partial_failures(self):
        """Khi có nhiều job đến hạn, một job bắn exception không được ảnh hưởng đến các job khác."""
        scheduler = HomigoScheduler()
        fail_func = MagicMock(side_effect=Exception("Job A hỏng!"))
        success_func = MagicMock()

        job_a = scheduler.add_daily_job("job_a", "02:00", fail_func)
        job_b = scheduler.add_daily_job("job_b", "02:00", success_func)

        now = datetime(2026, 11, 6, 2, 5, 0)
        job_a.next_run = now - timedelta(minutes=5)
        job_b.next_run = now - timedelta(minutes=5)

        executed = scheduler.run_pending(now=now)

        assert "job_a" not in executed
        assert "job_b" in executed
        fail_func.assert_called_once()
        success_func.assert_called_once()
        assert not scheduler.lock.locked()


# ==============================================================================
# NHÓM 3 — CONCURRENCY & RACE CONDITION (NON-OVERLAPPING LOCK)
# ==============================================================================

class TestConcurrencyAndLock:
    """Kiểm tra cơ chế khoá Non-overlapping Lock và loại trừ lẫn nhau (Mutual Exclusion)."""

    def test_job_lock_property_accessible(self):
        """Kiểm tra thuộc tính job_lock tương đương lock."""
        scheduler = HomigoScheduler()
        assert scheduler.job_lock is scheduler.lock

    def test_non_overlapping_lock_skips_running_job(self):
        """Khi Job 1 đang chạy (giữ lock), Job 2 phải bị bỏ qua (skipped) an toàn."""
        scheduler = HomigoScheduler()

        job1_started = threading.Event()
        job1_allow_finish = threading.Event()
        job2_executed = threading.Event()

        def slow_job1():
            job1_started.set()
            job1_allow_finish.wait(timeout=5.0)

        def job2():
            job2_executed.set()

        scheduler.add_daily_job("job1", "02:00", slow_job1)
        scheduler.add_daily_job("job2", "02:00", job2)

        # Khởi chạy Job 1 trên thread nền
        thread1 = threading.Thread(target=lambda: scheduler.run_now("job1"))
        thread1.daemon = True
        thread1.start()

        # Chờ Job 1 bắt đầu và chiếm lock
        assert job1_started.wait(timeout=2.0)
        assert scheduler.lock.locked()

        # Thử kích hoạt Job 2 trong khi Job 1 đang chạy
        job2_result = scheduler.run_now("job2")
        assert job2_result is False
        assert not job2_executed.is_set()

        # Thử kích hoạt lại chính Job 1 trong khi phiên trước chưa xong
        job1_reentry = scheduler.run_now("job1")
        assert job1_reentry is False

        # Cho phép Job 1 kết thúc
        job1_allow_finish.set()
        thread1.join(timeout=2.0)
        assert not thread1.is_alive()

        # Lock đã được giải phóng, Job 2 giờ có thể chạy bình thường
        assert not scheduler.lock.locked()
        job2_retry = scheduler.run_now("job2")
        assert job2_retry is True
        assert job2_executed.is_set()

    def test_multithreaded_concurrent_execution_race_condition(self):
        """Mô phỏng 10 luồng kích hoạt đồng thời: Đảm bảo Mutual Exclusion không bao giờ > 1."""
        scheduler = HomigoScheduler()
        active_workers = 0
        max_concurrent_seen = 0
        state_lock = threading.Lock()
        execution_count = 0

        def concurrent_task():
            nonlocal active_workers, max_concurrent_seen, execution_count
            with state_lock:
                active_workers += 1
                if active_workers > max_concurrent_seen:
                    max_concurrent_seen = active_workers
                execution_count += 1

            # Giả lập thời gian xử lý ETL ngắn
            time.sleep(0.05)

            with state_lock:
                active_workers -= 1

        scheduler.add_daily_job("stress_job", "02:00", concurrent_task)

        # Sử dụng Barrier để đồng bộ hoá 10 luồng cùng lao vào 1 tích tắc
        thread_count = 10
        barrier = threading.Barrier(thread_count)
        results = [None] * thread_count

        def worker(idx):
            barrier.wait()
            results[idx] = scheduler.run_now("stress_job")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(thread_count)]
        for t in threads:
            t.daemon = True
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        # Số lượng tiến trình chạy đồng thời bên trong job KHÔNG BAO GIỜ vượt quá 1
        assert max_concurrent_seen == 1
        # Chính xác 1 luồng thành công lấy lock, 9 luồng còn lại bị từ chối
        success_count = sum(1 for r in results if r is True)
        assert success_count == 1
        assert execution_count == 1
        assert not scheduler.lock.locked()


# ==============================================================================
# NHÓM 4 — INTEGRATION & GRACEFUL SHUTDOWN
# ==============================================================================

class TestIntegrationAndGracefulShutdown:
    """Kiểm tra cơ chế ngắt vòng lặp an toàn và tích hợp CLI Runner."""

    def test_graceful_shutdown_terminates_start_loop(self):
        """Gọi scheduler.stop() kích hoạt stop_event và dừng start() ngay lập tức."""
        scheduler = HomigoScheduler()
        scheduler.setup_default_jobs()

        start_thread = threading.Thread(target=lambda: scheduler.start(poll_interval=0.05))
        start_thread.daemon = True
        start_thread.start()

        # Đợi scheduler khởi động
        time.sleep(0.1)
        assert scheduler._is_running is True

        # Gọi stop() để yêu cầu dừng an toàn
        scheduler.stop()

        # Thread phải kết thúc nhanh chóng, không bị kẹt vô tận
        start_thread.join(timeout=2.0)
        assert not start_thread.is_alive()
        assert scheduler._is_running is False

    @patch("crawler.scheduler.print")
    def test_print_schedule_summary_does_not_crash(self, mock_print):
        """print_schedule_summary() in bảng trực quan rõ ràng, không lỗi."""
        scheduler = HomigoScheduler()
        scheduler.setup_default_jobs()
        scheduler.print_schedule_summary()
        assert mock_print.called

    def test_cli_argument_parsing_defaults(self):
        """parse_args() trả về giá trị mặc định khi không truyền cờ nào."""
        args = parse_args([])
        assert args.run_now is None
        assert args.pages is None
        assert args.limit is None
        assert args.region is None
        assert args.source is None
        assert args.no_clean is False
        assert args.poll_interval == 1.0

    @pytest.mark.parametrize(
        "run_now_flag",
        ["daily", "update", "verify", "weekly"],
    )
    def test_cli_argument_parsing_run_now_valid_choices(self, run_now_flag):
        """parse_args() chấp nhận các giá trị hợp lệ cho --run-now."""
        args = parse_args(["--run-now", run_now_flag])
        assert args.run_now == run_now_flag

    def test_cli_argument_parsing_invalid_choice(self):
        """parse_args() với giá trị không hợp lệ cho --run-now sẽ thoát với mã lỗi SystemExit."""
        with pytest.raises(SystemExit):
            parse_args(["--run-now", "invalid_mode"])

    def test_cli_argument_parsing_all_override_flags(self):
        """parse_args() parse chuẩn xác toàn bộ các cờ ghi đè."""
        cli_input = [
            "--run-now", "daily",
            "--pages", "10",
            "--limit", "250",
            "--region", "hcm",
            "--source", "phongtro123",
            "--no-clean",
            "--poll-interval", "2.5",
        ]
        args = parse_args(cli_input)
        assert args.run_now == "daily"
        assert args.pages == 10
        assert args.limit == 250
        assert args.region == "hcm"
        assert args.source == "phongtro123"
        assert args.no_clean is True
        assert args.poll_interval == 2.5

    @patch("crawler.scheduler.run_crawl_job")
    def test_main_run_now_demo_mode_success(self, mock_crawl):
        """Hàm main() với cờ --run-now kích hoạt job ngay và thoát mã 0."""
        with pytest.raises(SystemExit) as exit_info:
            main(["--run-now", "daily", "--pages", "2"])

        assert exit_info.value.code == 0
        mock_crawl.assert_called_once()
        call_kwargs = mock_crawl.call_args.kwargs
        assert call_kwargs["pages"] == 2
        assert call_kwargs["mode"] == "update"

    @patch("crawler.scheduler.run_crawl_job", side_effect=Exception("ETL Fail"))
    def test_main_run_now_demo_mode_failure(self, mock_crawl):
        """Hàm main() với cờ --run-now khi job lỗi thì thoát với mã 1."""
        with pytest.raises(SystemExit) as exit_info:
            main(["--run-now", "verify"])

        assert exit_info.value.code == 1
        mock_crawl.assert_called_once()
