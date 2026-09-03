import gzip
import logging
import os
import shutil
from logging.handlers import RotatingFileHandler
from typing import Any, Final, LiteralString, TextIO

CRITICAL = logging.CRITICAL
ERROR = logging.ERROR
WARNING = logging.WARNING
INFO = logging.INFO
DEBUG = logging.DEBUG
NOTSET = logging.NOTSET


class GZipRotatingFileHandler(RotatingFileHandler):
    """
    ログを .gz 形式でローテーション保存するカスタムハンドラ。
    """

    def doRollover(self) -> None:
        super().doRollover()

        for i in range(self.backupCount, 0, -1):
            filename: str = f"{self.baseFilename}.{i}"
            gz_filename: str = f"{filename}.gz"

            if os.path.exists(filename) and not os.path.exists(gz_filename):
                with (
                    open(filename, "rb") as f_in,
                    gzip.open(gz_filename, "wb") as f_out,
                ):
                    shutil.copyfileobj(f_in, f_out)
                os.remove(filename)


class AppLogger:
    def __init__(
        self,
        name: str,
        formatter: logging.Formatter,
        *,
        to_console: bool = True,
        to_file: str | None = None,
        # level: int = logging.WARNING,
        level: int = logging.INFO,
        rotate_size: int = 300 * 1024 * 1024,
        backup_count: int = 1,
        compress: bool = True,
    ) -> None:
        # NOTE: to__console=False(コンソール出力なし) かつ to_file = None(ファイル出力なし)でAppLoggerを作成した場合、
        #       .warning("文字列")等を使用するとコンソールに文字列がそのまま出力される。(formatterでの指定が効かない)
        self.name: Final[str] = name
        self._logger: logging.Logger = logging.getLogger(name)
        self._logger.handlers.clear()

        self.update(
            formatter=formatter,
            to_console=to_console,
            to_file=to_file,
            level=level,
            rotate_size=rotate_size,
            backup_count=backup_count,
            compress=compress,
        )

        self._logger.propagate = False

    def is_enabled_for(self, level: int) -> bool:
        return self._logger.isEnabledFor(level)

    def update(
        self,
        formatter: logging.Formatter,
        *,
        to_console: bool = True,
        to_file: str | None = None,
        level: int,
        rotate_size: int = 300 * 1024 * 1024,
        backup_count: int = 1,
        compress: bool = True,
    ) -> None:
        """
        インスタンス内に持つlogging.Loggerを更新する
        """
        # NOTE: to__console=False(コンソール出力なし) かつ to_file = None(ファイル出力なし)でAppLoggerを更新した場合、
        #       .warning("文字列")等を使用するとコンソールに文字列がそのまま出力される。(formatterでの指定が効かない)
        self._logger.handlers.clear()
        self._logger.setLevel(level)

        if to_console:
            ch: logging.StreamHandler[TextIO] = self._create_console_handler(formatter)
            self._logger.addHandler(ch)

        if to_file:
            fh: RotatingFileHandler = self._create_file_handler(
                formatter, to_file, rotate_size, backup_count, compress
            )
            self._logger.addHandler(fh)

    # NOTE: log等ログ出力用のメソッドは可変長引数を取るため、Any以外の型ヒントは不適となるのでRuffのルール除外する
    def log(self, level: int, msg: object, *args: object, **kwargs: Any) -> None:  # noqa: ANN401
        self._logger.log(level, msg, *args, **kwargs)

    def debug(self, msg: object, *args: object, **kwargs: Any) -> None:  # noqa: ANN401
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: object, *args: object, **kwargs: Any) -> None:  # noqa: ANN401
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: object, *args: object, **kwargs: Any) -> None:  # noqa: ANN401
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: object, *args: object, **kwargs: Any) -> None:  # noqa: ANN401
        self._logger.error(msg, *args, **kwargs)

    def critical(self, msg: object, *args: object, **kwargs: Any) -> None:  # noqa: ANN401
        self._logger.critical(msg, *args, **kwargs)

    def exception(self, msg: object, *args: object, **kwargs: Any) -> None:  # noqa: ANN401
        self._logger.exception(msg, *args, **kwargs)

    def _create_file_handler(
        self,
        formatter: logging.Formatter,
        file_path: str,
        rotate_size: int = 300 * 1024 * 1024,
        backup_count: int = 1,
        compress: bool = True,
    ) -> RotatingFileHandler:
        log_dir: str = os.path.dirname(file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        if compress:
            fh = GZipRotatingFileHandler(
                file_path,
                maxBytes=rotate_size,
                backupCount=backup_count,
                encoding="utf-8",
            )
        else:
            fh = RotatingFileHandler(
                file_path,
                maxBytes=rotate_size,
                backupCount=backup_count,
                encoding="utf-8",
            )
        fh.setFormatter(formatter)
        return fh

    def _create_console_handler(
        self,
        formatter: logging.Formatter,
    ) -> logging.StreamHandler[TextIO]:
        ch: logging.StreamHandler[TextIO] = logging.StreamHandler()
        ch.setFormatter(formatter)
        return ch


class AppLoggerFactory:
    __DEFAULT_TO_CONSOLE = True
    __DEFAULT_TO_FILE = None
    #__DEFAULT_LEVEL: int = logging.WARNING
    __DEFAULT_LEVEL: int = logging.INFO
    __DEFAULT_INCLUDE_TIME = True
    __DEFAULT_ROTATE_SIZE: int = 300 * 1024 * 1024
    __DEFAULT_BACKUP_COUNT: int = 1
    __DEFAULT_COMPRESS: bool = True

    def __init__(
        self,
        *,
        to_console: bool | None = None,
        to_file: str | None = None,
        level: int | None = None,
        include_time: bool | None = None,
        rotate_size: int | None = None,
        backup_count: int | None = None,
        compress: bool | None = None,
    ) -> None:
        self._loggers: list[AppLogger] = []

        self._to_console: bool = (
            self.__DEFAULT_TO_CONSOLE if to_console is None else to_console
        )
        self._to_file: str | None = (
            self.__DEFAULT_TO_FILE if to_file is None else to_file
        )
        self._level: int = self.__DEFAULT_LEVEL if level is None else level
        self._include_time: bool = (
            self.__DEFAULT_INCLUDE_TIME if include_time is None else include_time
        )
        self._rotate_size: int = (
            self.__DEFAULT_ROTATE_SIZE if rotate_size is None else rotate_size
        )
        self._backup_count: int = (
            self.__DEFAULT_BACKUP_COUNT if backup_count is None else backup_count
        )
        self._compress: bool = self.__DEFAULT_COMPRESS if compress is None else compress

    def update(self) -> None:
        """
        管理下にある全てのAppLoggerをデフォルト値で更新する
        """

        formatter: logging.Formatter = self.__get_formatter(self._include_time)

        for logger in self._loggers:
            logger.update(
                formatter=formatter,
                to_console=self._to_console,
                to_file=self._to_file,
                level=self._level,
                rotate_size=self._rotate_size,
                backup_count=self._backup_count,
                compress=self._compress,
            )

    def append_logger(self, logger: AppLogger) -> None:
        self._loggers.append(logger)

    def register_from_name(
        self,
        name: str,
        *,
        to_console: bool | None = None,
        to_file: str | None = None,
        level: int | None = None,
        include_time: bool | None = None,
        rotate_size: int | None = None,
        backup_count: int | None = None,
        compress: bool | None = None,
    ) -> AppLogger:
        # 引数が渡された場合は、インスタンスのデフォルト値ではなく引数の値を使う
        _to_console: bool = self._to_console if to_console is None else to_console
        _to_file: str | None = self._to_file if to_file is None else to_file
        _level: int = self._level if level is None else level
        _include_time: bool = (
            self._include_time if include_time is None else include_time
        )
        _rotate_size: int = self._rotate_size if rotate_size is None else rotate_size
        _backup_count: int = (
            self._backup_count if backup_count is None else backup_count
        )
        _compress: bool = self._compress if compress is None else compress

        logger: AppLogger = self.from_name(
            name,
            to_console=_to_console,
            to_file=_to_file,
            level=_level,
            include_time=_include_time,
            rotate_size=_rotate_size,
            backup_count=_backup_count,
            compress=_compress,
        )
        self._loggers.append(logger)

        return logger

    def register_from_type(self, t: type[Any]) -> AppLogger:
        return self.register_from_name(t.__name__)

    @classmethod
    def from_name(
        cls,
        name: str,
        *,
        to_console: bool | None = None,
        to_file: str | None = None,
        level: int | None = None,
        include_time: bool | None = None,
        rotate_size: int | None = None,
        backup_count: int | None = None,
        compress: bool | None = None,
    ) -> AppLogger:
        # 引数が渡された場合は、デフォルト値ではなく引数の値を使う
        _to_console: bool = (
            cls.__DEFAULT_TO_CONSOLE if to_console is None else to_console
        )
        _to_file: str | None = cls.__DEFAULT_TO_FILE if to_file is None else to_file
        _level: int = cls.__DEFAULT_LEVEL if level is None else level
        _include_time: bool = (
            cls.__DEFAULT_INCLUDE_TIME if include_time is None else include_time
        )
        _rotate_size: int = (
            cls.__DEFAULT_ROTATE_SIZE if rotate_size is None else rotate_size
        )
        _backup_count: int = (
            cls.__DEFAULT_BACKUP_COUNT if backup_count is None else backup_count
        )
        _compress: bool = cls.__DEFAULT_COMPRESS if compress is None else compress

        formatter: logging.Formatter = cls.__get_formatter(_include_time)

        return AppLogger(
            name,
            formatter=formatter,
            to_console=_to_console,
            to_file=_to_file,
            level=_level,
            rotate_size=_rotate_size,
            backup_count=_backup_count,
            compress=_compress,
        )

    @classmethod
    def from_type(cls, t: type[Any]) -> AppLogger:
        return cls.from_name(t.__name__)

    @classmethod
    def __get_formatter(cls, include_time: bool) -> logging.Formatter:
        if include_time:
            fmt: LiteralString = "%(name)s - %(asctime)s - %(levelname)s - %(message)s"
        else:
            fmt: LiteralString = "%(name)s - %(levelname)s - %(message)s"
        return logging.Formatter(fmt)


if __name__ == "__main__":
    # from_typeでloggerを生成
    from_type_logger: AppLogger = AppLoggerFactory.from_type(AppLoggerFactory)
    from_type_logger.warning("from_typeで出力")

    """
    以下3項目に分けて動作確認
    出力先の設定
        ・to_console, to_file,
    出力内容の設定
        ・level, include_time,
    ファイルへの保存形式の設定
        ・rotate_size, backup_count, compress,
    """
    # 出力先の設定
    # consoleとfile両方に出力しない
    notto_console_notto_file: AppLogger = AppLoggerFactory.from_name(
        "notto_console_notto_file", to_console=False
    )
    notto_console_notto_file.warning("これは出力されない")

    # consoleとfile両方に出力
    to_console_and_file: AppLogger = AppLoggerFactory.from_name(
        "to_console_and_file",
        to_file="./mylog.log",
        to_console=True,
        compress=False,
    )
    to_console_and_file.warning("これはファイルとコンソール両方に出力される")

    # 出力内容の設定
    # levelとinclude_timeがデフォルト
    _logger1: AppLogger = AppLoggerFactory.from_name(
        "logger1",
    )
    _logger1.debug("これは出力されない")
    _logger1.info("これは出力されない")
    _logger1.warning("時間表示あり、WARNING以上を表示")
    _logger1.error("時間表示あり、WARNING以上を表示")
    _logger1.critical("時間表示あり、WARNING以上を表示")

    # levelをINFO、include_timeを非表示
    _logger2: AppLogger = AppLoggerFactory.from_name(
        "logger2", level=logging.INFO, include_time=False
    )
    _logger2.debug("これは出力されない")
    _logger2.info("時間表示なし、INFO以上を表示")
    _logger2.warning("時間表示なし、INFO以上を表示")
    _logger2.error("時間表示なし、INFO以上を表示")
    _logger2.critical("時間表示なし、INFO以上を表示")

    # ファイルへの保存形式の設定
    # 圧縮、１ファイル、サイズ小
    compress_logger1: AppLogger = AppLoggerFactory.from_name(
        "compress_logger1",
        to_file="./mylog.gz",
        rotate_size=1024,
        backup_count=1,
        compress=True,
        to_console=False,
    )

    # 圧縮、複数ファイル、サイズ大
    compress_logger2: AppLogger = AppLoggerFactory.from_name(
        "compress_logger2",
        to_file="./mylogs.gz",
        rotate_size=10 * 1024,
        backup_count=4,
        compress=True,
        to_console=False,
    )

    # 非圧縮、１ファイル、サイズ大
    un_compress_logger1: AppLogger = AppLoggerFactory.from_name(
        "un_compress_logger1",
        to_file="./mylog",
        rotate_size=10 * 1024,
        backup_count=1,
        compress=False,
        to_console=False,
    )
    # 非圧縮、複数ファイル、サイズ小
    un_compress_logger2: AppLogger = AppLoggerFactory.from_name(
        "un_compress_logger2",
        to_file="./mylogs",
        rotate_size=1024,
        backup_count=4,
        compress=False,
        to_console=False,
    )

    for i in range(100):
        compress_logger1.warning(f"圧縮、１ファイル、サイズ小ファイルログ{i}")
        compress_logger2.warning(f"圧縮、複数ファイル、サイズ大ファイルログ{i}")
        un_compress_logger1.warning(f"非圧縮、１ファイル、サイズ大ファイルログ{i}")
        un_compress_logger2.warning(f"非圧縮、複数ファイル、サイズ小ファイルログ{i}")

    # AppLoggerFactoryのインスタンス化とupdateの確認
    app_logger_factory = AppLoggerFactory(to_file="./ALF_logs.txt")
    applogger1: AppLogger = app_logger_factory.register_from_name(
        "applogger1", level=logging.INFO
    )
    applogger2: AppLogger = app_logger_factory.register_from_name(
        "applogger2", level=logging.WARNING
    )
    applogger3 = app_logger_factory.from_name(
        "applogger3", to_file="", compress=False, level=10, include_time=False
    )

    applogger1.info("時間表示あり、INFO以上を表示、ファイル出力あり")
    applogger1.warning("時間表示あり、INFO以上を表示、ファイル出力あり")
    applogger1.error("時間表示あり、INFO以上を表示、ファイル出力あり")
    applogger1.critical("時間表示あり、INFO以上を表示、ファイル出力あり")
    applogger1.exception("exception:時間表示あり、INFO以上を表示、ファイル出力あり")

    applogger2.info("出力されない")
    applogger2.warning("時間表示あり、WARNING以上を表示、ファイル出力あり")
    applogger2.error("時間表示あり、WARNING以上を表示、ファイル出力あり")
    applogger2.critical("時間表示あり、WARNING以上を表示、ファイル出力あり")
    applogger2.exception("exception:時間表示あり、WARNING以上を表示、ファイル出力あり")
    applogger3.info("時間表示なし、INFO以上を表示、ファイル出力なし")
    applogger3.warning("時間表示なし、INFO以上を表示、ファイル出力なし")
    applogger3.error("時間表示なし、INFO以上を表示、ファイル出力なし")
    applogger3.critical("時間表示なし、INFO以上を表示、ファイル出力なし")
    applogger3.exception("exception:時間表示なし、INFO以上を表示、ファイル出力なし")
    app_logger_factory.append_logger(applogger3)
    app_logger_factory.update()
    applogger3.info("出力されない")
    applogger3.warning("時間表示あり、WARNING以上を表示、ファイル出力あり")
    applogger3.error("時間表示あり、WARNING以上を表示、ファイル出力あり")
    applogger3.critical("時間表示あり、WARNING以上を表示、ファイル出力あり")
    applogger3.exception("exception:時間表示あり、WARNING以上を表示、ファイル出力あり")
    # printf風表記の確認
    applogger3.warning("int:%d, float:%f, hex:0x%X", 100, 3.14, 65534)
