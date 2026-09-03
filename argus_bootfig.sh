#!/bin/bash
set -e
source ~/.profile

# ARGUS3D開発者モード
# Godot UIにて画面ログの記録時間の上限がなくなる. (製品仕様は30分で強制終了)
export ARGUS3D_DEV=1
echo $ARGUS3D_DEV

# プロジェクトディレクトリに移動
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# 仮想環境（.venv）のPythonのパスを動的に定義（ベタ書き回避）
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

############### 要設定 ##################
# 仮想環境を有効化
# source p312/bin/activate
source .venv/bin/activate
###########################################

# settings.ini のデータパスの書き換えをここで行う場合
DATA_DIR=/mnt/nvme
#DATA_DIR=/home/matsuoka/data/X6T304
CAL_DATA_DIR=/mnt/nvme
#CAL_DATA_DIR=/home/matsuoka
#sed -i "s|^data_dir *=.*|data_dir = ${DATA_DIR}|g" config/settings.ini
#sed -i "s|^data_dir *=.*|data_dir = ${CAL_DATA_DIR}|g" config/calib_settings.ini

CONFIG_DIR="./config"
LOG_DIR="./log"
MMAP_DIR="/dev/shm"

# ステータスMMAPのパス
MMAP_FILE="${MMAP_DIR}/status.mmap"

RUN_USER="$(id -un)"
RUN_GROUP="$(id -gn)"

# RAM領域にMMAP作成
sudo "$VENV_PYTHON" ./scripts/prepare_argus.py \
    --config-dir "$CONFIG_DIR" \
    --log-dir "$LOG_DIR" \
    --mmap-dir "$MMAP_DIR" \
    --user "$RUN_USER" \
    --group "$RUN_GROUP"

# 起動モード
# engine : Godot Engine + project_dir
# appimage : AppImage 単体起動
UI_MODE="${1:-appimage}"

case "$UI_MODE" in
    engine|appimage)
        ;;
    *)
        echo "Usage: $0 [engine|appimage]"
        exit 1
        ;;
esac

export ARGUS_UI_MODE="$UI_MODE"

# PYTHONPATHを設定（相対import対策）
export PYTHONPATH="$PWD"

# 起動時画像のパス
BOOT_IMAGE="./config/fig/Splash_booting.png"

stop_service() {
    local pid="$1"
    local name="$2"

    if ! kill -0 "$pid" 2>/dev/null; then
        wait "$pid" 2>/dev/null || true
        return
    fi

    echo "<<run_all>> ${name} に終了要求を送信 (PID=${pid})"
    kill -INT "$pid" 2>/dev/null || true

    for _ in {1..30}; do
        if ! kill -0 "$pid" 2>/dev/null; then
            wait "$pid" 2>/dev/null || true
            return
        fi
        sleep 1
    done

    echo "<<run_all>> WARN: ${name} が停止しないためプロセスグループを終了"
    kill -TERM -- "-${pid}" 2>/dev/null || true
    sleep 3
    kill -KILL -- "-${pid}" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
}

cleanup() {
    trap - EXIT INT TERM

    echo "<<run_all>> cleanup start"

    [ -n "$MAIN_PID" ] && stop_service "$MAIN_PID" "Main"
    [ -n "$MONITOR_PID" ] && stop_service "$MONITOR_PID" "MonitorArgus"
    [ -n "$BOOT_IMAGE_PID" ] && pkill -TERM -P "$BOOT_IMAGE_PID" 2>/dev/null || true
    [ -n "$BOOT_IMAGE_PID" ] && kill -TERM "$BOOT_IMAGE_PID" 2>/dev/null || true
    [ -n "$BOOT_IMAGE_PID" ] && wait "$BOOT_IMAGE_PID" 2>/dev/null || true

    echo "<<run_all>> cleanup end"
}

trap cleanup EXIT INT TERM

# ----------------------------
# 起動画像の表示監視関数（SHUTDOWN or REBOOT時に表示、RUNNINGで非表示）
# ----------------------------
monitor_boot_img() {
    FEH_PID=0

    while true; do
        if [ -f "$MMAP_FILE" ]; then
            read STATUS STATUS_NAME <<< "$("$VENV_PYTHON" ./argus_synchro/SystemMonitor/get_status.py --mmap-dir "$MMAP_DIR")"

            if ! [[ "$STATUS" =~ ^-?[0-9]+$ ]]; then
                echo "<<monitor_status>> invalid status: $STATUS $STATUS_NAME"
                sleep 0.5
                continue
            fi

            echo "<<monitor_status>> present status: $STATUS_NAME ($STATUS)"

            if [ "$STATUS" -eq -1 ] || [ "$STATUS" -eq 1 ]; then
                if [ -f "$BOOT_IMAGE" ] && ! ps -p "$FEH_PID" > /dev/null 2>&1; then
                    echo "<<monitor_status>> 起動画像表示"
                    # feh -F "$BOOT_IMAGE" &
                    feh --geometry 1920x1080 "$BOOT_IMAGE" &
                    FEH_PID=$!
                fi

            elif [ "$STATUS" -eq 3 ]; then
                # RUNNING
                if ps -p "$FEH_PID" > /dev/null 2>&1; then
                    echo "<<monitor_status>> 起動画像を非表示"
                    kill -INT "$FEH_PID"
                    wait "$FEH_PID" 2>/dev/null
                    FEH_PID=0
                fi
            fi
        fi

        sleep 0.5
    done
}

# ----------------------------
# 画像監視をバックグラウンド実行
# ----------------------------
monitor_boot_img &
BOOT_IMAGE_PID=$!

# ----------------------------
# MonitorArgus を バックグラウンド起動
# ----------------------------
setsid "$VENV_PYTHON" -m argus_synchro.SystemMonitor.MonitorArgus \
    --config-dir "$CONFIG_DIR" \
    --log-dir "$LOG_DIR" \
    --mmap-dir "$MMAP_DIR" &
MONITOR_PID=$!

echo "<<run_all>> MonitorArgus 起動 (PID=$MONITOR_PID, UI_MODE=$ARGUS_UI_MODE)"

sleep 1

if ! ps -p "$MONITOR_PID" > /dev/null 2>&1; then
    echo "<<run_all>> ERROR: MonitorArgus が起動直後に終了しました"
    exit 1
fi

# ----------------------------
# mmapファイルが作成されるまで最大10秒待機
# ----------------------------
for i in {1..10}; do
    if [ -f "$MMAP_FILE" ]; then
        echo "<<run_all>> status.mmap 検出"
        break
    fi

    echo "<<run_all>> waiting mmap ... ($i)"
    sleep 1
done

# ----------------------------
# Main.py を バックグラウンド起動
# ----------------------------
setsid "$VENV_PYTHON" -m argus_synchro \
    --config-dir "$CONFIG_DIR" \
    --log-dir "$LOG_DIR" \
    --mmap-dir "$MMAP_DIR" &
MAIN_PID=$!

echo "<<run_all>> Main.py 起動 (PID=$MAIN_PID)"

# ----------------------------
# BOOTING 状態になるまで最大10秒待機
# ----------------------------
for i in {1..10}; do
    read STATUS STATUS_NAME <<< "$("$VENV_PYTHON" ./argus_synchro/SystemMonitor/get_status.py --mmap-dir "$MMAP_DIR")"

    if ! [[ "$STATUS" =~ ^-?[0-9]+$ ]]; then
        echo "<<run_all>> invalid status: $STATUS $STATUS_NAME"
        sleep 1
        continue
    fi

    if [ "$STATUS" -eq 2 ]; then
        echo "<<run_all>> ステータスが BOOTING に遷移"
        break
    fi

    echo "<<run_all>> ステータス待機中... (現在: $STATUS_NAME $STATUS)"
    sleep 1
done

# ----------------------------
# Main.py の終了待ち
# ----------------------------
wait "$MAIN_PID"

echo "<<run_all>> Main.py 終了、MonitorArgus を停止"

# Monitor を終了（SIGINT）
stop_service "$MONITOR_PID" "MonitorArgus"

# スプラッシュ監視を終了
pkill -TERM -P "$BOOT_IMAGE_PID" 2>/dev/null || true
kill -INT "$BOOT_IMAGE_PID" 2>/dev/null || true
wait "$BOOT_IMAGE_PID" 2>/dev/null || true

trap - EXIT INT TERM

echo "<<run_all>> 全プロセス終了"
