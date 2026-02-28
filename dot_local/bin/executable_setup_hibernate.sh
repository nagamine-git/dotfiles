#!/usr/bin/env bash
set -eu

# ハイバネート環境セットアップ（ThinkPad E14 Gen6 Ryzen / EndeavourOS）
# 実行条件: sudo 権限、十分なディスク空き
# 作成物: swapfile、カーネルresume引数、mkinitcpio resume hook

SWAPFILE="/swapfile"
SWAP_SIZE_GB=18  # RAM 16GB の場合、RAM+2GB が推奨

print_status() { printf '\033[1;34m>> %s\033[0m\n' "$1"; }
print_warn()   { printf '\033[1;33m!! %s\033[0m\n' "$1"; }
print_ok()     { printf '\033[1;32mOK %s\033[0m\n' "$1"; }
print_err()    { printf '\033[1;31mERR %s\033[0m\n' "$1"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_err "root 権限が必要: sudo $0"
        exit 1
    fi
}

get_ram_gb() {
    awk '/MemTotal/ {printf "%.0f", $2/1024/1024}' /proc/meminfo
}

check_current_swap() {
    local swap_total
    swap_total=$(awk '/SwapTotal/ {print $2}' /proc/meminfo)
    if [[ $swap_total -gt 0 ]]; then
        local swap_gb
        swap_gb=$(awk '/SwapTotal/ {printf "%.1f", $2/1024/1024}' /proc/meminfo)
        print_status "既存swap: ${swap_gb}GB"
        return 0
    fi
    return 1
}

check_sleep_state() {
    print_status "利用可能なスリープ状態:"
    cat /sys/power/state 2>/dev/null || print_warn "/sys/power/state が読めない"
    
    if [[ -f /sys/power/mem_sleep ]]; then
        print_status "mem_sleep: $(cat /sys/power/mem_sleep)"
    fi
    
    if [[ -f /sys/power/disk ]]; then
        print_status "disk: $(cat /sys/power/disk)"
    fi
}

create_swapfile() {
    if [[ -f "$SWAPFILE" ]]; then
        local current_size
        current_size=$(stat -c%s "$SWAPFILE" 2>/dev/null || echo 0)
        local needed_bytes=$((SWAP_SIZE_GB * 1024 * 1024 * 1024))
        if [[ $current_size -ge $needed_bytes ]]; then
            print_ok "swapfile 既存 ($(numfmt --to=iec "$current_size"))"
            return 0
        fi
        print_warn "swapfile サイズ不足。再作成する"
        swapoff "$SWAPFILE" 2>/dev/null || true
        rm -f "$SWAPFILE"
    fi
    
    local free_gb
    free_gb=$(df -BG / | awk 'NR==2 {gsub(/G/,"",$4); print $4}')
    if [[ $free_gb -lt $((SWAP_SIZE_GB + 5)) ]]; then
        print_err "ディスク空き不足: ${free_gb}GB (必要: $((SWAP_SIZE_GB + 5))GB)"
        exit 1
    fi
    
    print_status "swapfile 作成中 (${SWAP_SIZE_GB}GB)..."
    dd if=/dev/zero of="$SWAPFILE" bs=1G count="$SWAP_SIZE_GB" status=progress
    chmod 600 "$SWAPFILE"
    mkswap "$SWAPFILE"
    swapon "$SWAPFILE"
    print_ok "swapfile 作成完了"
    
    if ! grep -q "$SWAPFILE" /etc/fstab; then
        echo "$SWAPFILE none swap defaults 0 0" >> /etc/fstab
        print_ok "fstab に追加"
    fi
}

get_swap_offset() {
    if ! command -v filefrag >/dev/null 2>&1; then
        print_err "filefrag が見つからない"
        exit 1
    fi
    filefrag -v "$SWAPFILE" | awk 'NR==4 {gsub(/\./,"",$4); print $4}'
}

get_swap_partition() {
    df "$SWAPFILE" --output=source | tail -1
}

setup_kernel_resume() {
    local swap_device swap_offset
    swap_device=$(get_swap_partition)
    swap_offset=$(get_swap_offset)
    
    local swap_uuid
    swap_uuid=$(blkid -s UUID -o value "$swap_device")
    
    print_status "resume デバイス: $swap_device (UUID=$swap_uuid)"
    print_status "resume offset: $swap_offset"
    
    local grub_file="/etc/default/grub"
    if [[ -f "$grub_file" ]]; then
        local resume_param="resume=UUID=$swap_uuid resume_offset=$swap_offset"
        if grep -q "resume=" "$grub_file"; then
            print_warn "既存の resume パラメータを更新"
            sed -i "s|resume=[^ \"]*||g; s|resume_offset=[^ \"]*||g" "$grub_file"
        fi
        sed -i "s|GRUB_CMDLINE_LINUX_DEFAULT=\"|GRUB_CMDLINE_LINUX_DEFAULT=\"$resume_param |" "$grub_file"
        grub-mkconfig -o /boot/grub/grub.cfg 2>/dev/null || true
        print_ok "GRUB 更新完了"
    fi
    
    local loader_dir="/boot/loader/entries"
    if [[ -d "$loader_dir" ]]; then
        for entry in "$loader_dir"/*.conf; do
            if [[ -f "$entry" ]] && ! grep -q "resume=" "$entry"; then
                sed -i "/^options/ s/$/ resume=UUID=$swap_uuid resume_offset=$swap_offset/" "$entry"
                print_ok "systemd-boot エントリ更新: $(basename "$entry")"
            fi
        done
    fi
}

setup_mkinitcpio() {
    local initcpio="/etc/mkinitcpio.conf"
    if [[ ! -f "$initcpio" ]]; then
        print_warn "mkinitcpio.conf が見つからない"
        return 1
    fi
    
    if grep -q "resume" "$initcpio" && grep "HOOKS=" "$initcpio" | grep -q "resume"; then
        print_ok "resume hook 設定済み"
        return 0
    fi
    
    print_status "resume hook を追加中..."
    sed -i 's/\(HOOKS=.*\)filesystems/\1resume filesystems/' "$initcpio"
    
    mkinitcpio -P
    print_ok "initramfs 再構築完了"
}

verify_setup() {
    print_status "=== 検証 ==="
    
    local ok=true
    
    if swapon --show | grep -q "$SWAPFILE"; then
        print_ok "swap 有効"
    else
        print_err "swap 無効"
        ok=false
    fi
    
    if grep -q "resume" /etc/mkinitcpio.conf 2>/dev/null; then
        print_ok "resume hook あり"
    else
        print_err "resume hook なし"
        ok=false
    fi
    
    if systemctl is-enabled systemd-logind >/dev/null 2>&1; then
        print_ok "logind 有効"
    fi
    
    for target in sleep suspend hibernate suspend-then-hibernate; do
        local state
        state=$(systemctl is-enabled "${target}.target" 2>/dev/null || echo "unknown")
        if [[ "$state" == "masked" ]]; then
            print_err "${target}.target がマスクされている → unmask する"
            systemctl unmask "${target}.target"
        else
            print_ok "${target}.target: $state"
        fi
    done
    
    check_sleep_state
    
    if [[ "$ok" == true ]]; then
        print_ok "ハイバネート設定完了。再起動後に有効になる"
    else
        print_warn "一部設定に問題あり。上記のエラーを確認"
    fi
}

main() {
    check_root
    
    local ram_gb
    ram_gb=$(get_ram_gb)
    SWAP_SIZE_GB=$((ram_gb + 2))
    
    print_status "RAM: ${ram_gb}GB → swapfile: ${SWAP_SIZE_GB}GB"
    print_status "=== ハイバネート環境セットアップ開始 ==="
    
    check_sleep_state
    create_swapfile
    setup_kernel_resume
    setup_mkinitcpio
    verify_setup
    
    echo ""
    print_status "=== 次のステップ ==="
    echo "1. 再起動する"
    echo "2. テスト: systemctl hibernate"
    echo "3. テスト: systemctl suspend-then-hibernate"
}

main "$@"
