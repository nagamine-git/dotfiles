#!/bin/bash

# ============================================
# 月配列2-263 タイピング練習ゲーム
# 段階的に使える文字が増えていく設計
# ============================================

# 色の定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# 各段の単語リスト（検証済み）
# 1段目：は・か・と・た・く・う・゛・き・れ
LEVEL1_WORDS=(
    "かた:型"
    "たか:鷹"
    "うた:歌"
    "きた:北"
    "くう:空"
    "かく:書く"
    "たく:炊く"
    "きく:聞く"
    "はく:履く"
    "たき:滝"
    "かき:柿"
    "うき:浮き"
    "かれ:彼"
    "たれ:垂れ"
    "だく:抱く"
    "がく:学"
    "たが:互い"
    "かが:加賀"
    "だれ:誰"
    "ばか:馬鹿"
)

# 2段目：＋そ・こ・し・て・ょ・つ・ん・い・の・り・ち
LEVEL2_WORDS=(
    "そこ:底"
    "しの:篠"
    "のり:海苔"
    "ちり:塵"
    "いし:石"
    "きつい:きつい"
    "こんき:根気"
    "しんり:心理"
    "りんご:林檎"
    "ことり:小鳥"
    "しょうき:正気"
    "こうしん:行進"
    "きょうと:京都"
    "りょうき:猟奇"
    "きんこ:金庫"
    "とんち:頓知"
    "しんこ:新古"
    "りょこう:旅行"
    "こきょう:故郷"
    "しょうりき:勝力"
)

# 3段目：＋す・け・に・な・さ・っ・る・、・。・゜
LEVEL3_WORDS=(
    "すな:砂"
    "けす:消す"
    "なつ:夏"
    "さる:猿"
    "ぱん:パン"
    "すっきり:すっきり"
    "なっとく:納得"
    "けっさく:傑作"
    "にっき:日記"
    "なつくさ:夏草"
    "すいっち:スイッチ"
    "けんさ:検査"
    "にんき:人気"
    "さっき:さっき"
    "さっぱり:さっぱり"
    "さんすう:算数"
    "なんきん:南京"
    "くっさく:掘削"
    "けんさく:検索"
    "にっすう:日数"
)

# 4段目：＋ぃ・を・ら・あ・よ・ま・お・も・わ・ゆ
LEVEL4_WORDS=(
    "あお:青"
    "まよう:迷う"
    "わら:藁"
    "ゆらり:揺らり"
    "おもい:思い"
    "あらい:荒い"
    "わらう:笑う"
    "おもう:思う"
    "ゆらゆら:ゆらゆら"
    "あまい:甘い"
    "おまわり:お巡り"
    "おもいやり:思いやり"
    "らいおん:ライオン"
    "まいにち:毎日"
    "ありがとう:有難う"
    "おもしろい:面白い"
    "わかもの:若者"
    "まんよう:万葉"
    "ゆういつ:唯一"
    "あらわす:表す"
)

# 5段目：＋ぁ・ひ・ほ・ふ・め・ぬ・え・み・や・ぇ・「・」
LEVEL5_WORDS=(
    "ひめ:姫"
    "ふえ:笛"
    "やみ:闇"
    "ぬの:布"
    "ぬめり:滑り"
    "ひふ:皮膚"
    "ふみ:文"
    "やめる:辞める"
    "みえ:三重"
    "えひめ:愛媛"
    "ひやけ:日焼け"
    "ふゆやすみ:冬休み"
    "めんえき:免疫"
    "ぬいもの:縫い物"
    "ふめい:不明"
    "ひみつ:秘密"
    "ふうふ:夫婦"
    "みやこ:都"
    "ほんや:本屋"
    "ぬくもり:温もり"
)

# 6段目：＋ぅ・へ・せ・ゅ・ゃ・む・ね・ろ・ー・ぉ
LEVEL6_WORDS=(
    "へや:部屋"
    "ねる:寝る"
    "むね:胸"
    "へそ:臍"
    "ねむい:眠い"
    "へいせい:平成"
    "せんろ:線路"
    "むしろ:寧ろ"
    "ねんれい:年齢"
    "ろーま:ローマ"
    "せいねん:青年"
    "むりょう:無料"
    "へんしゅう:編集"
    "ねっしん:熱心"
    "せかい:世界"
    "むせん:無線"
    "ろうねん:老年"
    "へいわ:平和"
    "せんせい:先生"
    "ねむりにつく:眠りにつく"
)

# ゲーム設定
WORDS_PER_ROUND=10
current_level=1
total_score=0
total_correct=0
total_wrong=0

# 配列の説明を表示
show_level_info() {
    local level=$1
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    case $level in
        1)
            echo -e "${BOLD}【レベル1】ホームポジション基本${NC}"
            echo -e "使える文字: ${YELLOW}は・か・と・た・く・う・゛・き・れ${NC}"
            echo -e "濁音: ${YELLOW}が・だ・ぐ・ば・ぎ${NC}"
            echo ""
            echo "  そ こ し て ょ  │  つ ん い の り ち"
            echo -e "  ${GREEN}は か ★ と た${NC}  │  ${GREEN}く う ★ ゛ き れ${NC}"
            echo "  す け に な さ  │  っ る 、 。 ゜ ・"
            ;;
        2)
            echo -e "${BOLD}【レベル2】上段追加${NC}"
            echo -e "追加文字: ${YELLOW}そ・こ・し・て・ょ・つ・ん・い・の・り・ち${NC}"
            echo ""
            echo -e "  ${GREEN}そ こ し て ょ${NC}  │  ${GREEN}つ ん い の り ち${NC}"
            echo -e "  ${GREEN}は か ★ と た${NC}  │  ${GREEN}く う ★ ゛ き れ${NC}"
            echo "  す け に な さ  │  っ る 、 。 ゜ ・"
            ;;
        3)
            echo -e "${BOLD}【レベル3】下段追加${NC}"
            echo -e "追加文字: ${YELLOW}す・け・に・な・さ・っ・る・゜${NC}"
            echo ""
            echo -e "  ${GREEN}そ こ し て ょ${NC}  │  ${GREEN}つ ん い の り ち${NC}"
            echo -e "  ${GREEN}は か ★ と た${NC}  │  ${GREEN}く う ★ ゛ き れ${NC}"
            echo -e "  ${GREEN}す け に な さ${NC}  │  ${GREEN}っ る 、 。 ゜${NC} ・"
            ;;
        4)
            echo -e "${BOLD}【レベル4】シフト面（左）${NC}"
            echo -e "追加文字: ${YELLOW}ぃ・を・ら・あ・よ・ま・お・も・わ・ゆ${NC}"
            echo ""
            echo "  [シフト面]"
            echo "  ぁ ひ ほ ふ め  │  ぬ え み や ぇ 「"
            echo -e "  ${GREEN}ぃ を ら あ よ${NC}  │  ${GREEN}ま お も わ ゆ${NC} 」"
            echo "  ぅ へ せ ゅ ゃ  │  む ろ ね ー ぉ"
            ;;
        5)
            echo -e "${BOLD}【レベル5】シフト面（上段）${NC}"
            echo -e "追加文字: ${YELLOW}ぁ・ひ・ほ・ふ・め・ぬ・え・み・や・ぇ${NC}"
            echo ""
            echo "  [シフト面]"
            echo -e "  ${GREEN}ぁ ひ ほ ふ め${NC}  │  ${GREEN}ぬ え み や ぇ${NC} 「"
            echo -e "  ${GREEN}ぃ を ら あ よ${NC}  │  ${GREEN}ま お も わ ゆ${NC} 」"
            echo "  ぅ へ せ ゅ ゃ  │  む ろ ね ー ぉ"
            ;;
        6)
            echo -e "${BOLD}【レベル6】全文字解禁！${NC}"
            echo -e "追加文字: ${YELLOW}ぅ・へ・せ・ゅ・ゃ・む・ね・ろ・ー・ぉ${NC}"
            echo ""
            echo "  [シフト面 - 完全版]"
            echo -e "  ${GREEN}ぁ ひ ほ ふ め${NC}  │  ${GREEN}ぬ え み や ぇ${NC} 「"
            echo -e "  ${GREEN}ぃ を ら あ よ${NC}  │  ${GREEN}ま お も わ ゆ${NC} 」"
            echo -e "  ${GREEN}ぅ へ せ ゅ ゃ${NC}  │  ${GREEN}む ろ ね ー ぉ${NC}"
            ;;
    esac
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# レベルに応じた単語配列を取得
get_words_for_level() {
    local level=$1
    case $level in
        1) echo "${LEVEL1_WORDS[@]}" ;;
        2) echo "${LEVEL2_WORDS[@]}" ;;
        3) echo "${LEVEL3_WORDS[@]}" ;;
        4) echo "${LEVEL4_WORDS[@]}" ;;
        5) echo "${LEVEL5_WORDS[@]}" ;;
        6) echo "${LEVEL6_WORDS[@]}" ;;
    esac
}

# 配列をシャッフル
shuffle_array() {
    local array=("$@")
    local i n temp
    n=${#array[@]}
    for ((i = n - 1; i > 0; i--)); do
        j=$((RANDOM % (i + 1)))
        temp="${array[i]}"
        array[i]="${array[j]}"
        array[j]="$temp"
    done
    echo "${array[@]}"
}

# タイトル画面
show_title() {
    clear
    echo -e "${CYAN}"
    echo "  ╔═══════════════════════════════════════════════════════════╗"
    echo "  ║                                                           ║"
    echo "  ║     月配列 2-263 タイピング練習ゲーム                      ║"
    echo "  ║     Tsuki Layout Typing Practice                          ║"
    echo "  ║                                                           ║"
    echo "  ╚═══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
    echo "  段階的に使える文字が増えていきます。"
    echo "  各レベルで使える文字のみで構成された単語を練習できます。"
    echo ""
    echo -e "  ${YELLOW}レベル1${NC}: ホームポジション（は・か・と・た・く・う・゛・き・れ）"
    echo -e "  ${YELLOW}レベル2${NC}: ＋上段（そ・こ・し・て・ょ・つ・ん・い・の・り・ち）"
    echo -e "  ${YELLOW}レベル3${NC}: ＋下段（す・け・に・な・さ・っ・る・゜）"
    echo -e "  ${YELLOW}レベル4${NC}: ＋シフト中段（ぃ・を・ら・あ・よ・ま・お・も・わ・ゆ）"
    echo -e "  ${YELLOW}レベル5${NC}: ＋シフト上段（ぁ・ひ・ほ・ふ・め・ぬ・え・み・や・ぇ）"
    echo -e "  ${YELLOW}レベル6${NC}: ＋シフト下段（ぅ・へ・せ・ゅ・ゃ・む・ね・ろ・ー・ぉ）"
    echo ""
    echo -e "  ${GREEN}開始するレベルを選んでください (1-6):${NC} "
}

# 結果表示
show_round_result() {
    local correct=$1
    local wrong=$2
    local time_taken=$3
    local wpm=$4
    
    echo ""
    echo -e "${CYAN}━━━━━━━━━━ ラウンド結果 ━━━━━━━━━━${NC}"
    echo -e "  正解: ${GREEN}$correct${NC} 問"
    echo -e "  ミス: ${RED}$wrong${NC} 問"
    echo -e "  時間: ${YELLOW}${time_taken}秒${NC}"
    if [ "$wpm" -gt 0 ]; then
        echo -e "  速度: ${MAGENTA}約${wpm}文字/分${NC}"
    fi
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# 最終結果表示
show_final_result() {
    echo ""
    echo -e "${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}                    ${BOLD}最終結果${NC}                              ${CYAN}║${NC}"
    echo -e "${CYAN}╠═══════════════════════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC}  総正解数: ${GREEN}$total_correct${NC} 問                                    ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  総ミス数: ${RED}$total_wrong${NC} 問                                     ${CYAN}║${NC}"
    
    if [ $((total_correct + total_wrong)) -gt 0 ]; then
        local accuracy=$((total_correct * 100 / (total_correct + total_wrong)))
        echo -e "${CYAN}║${NC}  正解率:   ${YELLOW}${accuracy}%${NC}                                       ${CYAN}║${NC}"
    fi
    
    echo -e "${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    if [ $total_correct -ge 50 ]; then
        echo -e "  ${GREEN}素晴らしい！月配列マスターへの道を歩んでいます！${NC}"
    elif [ $total_correct -ge 30 ]; then
        echo -e "  ${YELLOW}良い調子です！継続は力なり！${NC}"
    else
        echo -e "  ${CYAN}練習を続けましょう！毎日少しずつが大切です。${NC}"
    fi
    echo ""
}

# 画面クリアしてヘッダー再描画（配列プレビュー固定用）
redraw_screen() {
    local level=$1
    local correct=$2
    local wrong=$3
    local current_q=$4
    local total_q=$5
    
    clear
    
    # ヘッダー部分（固定表示）
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}月配列 2-263 タイピング練習${NC}  │  レベル $level  │  正解:${GREEN}$correct${NC} ミス:${RED}$wrong${NC}  │  問題:$current_q/$total_q"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    # 配列表示（コンパクト版）
    case $level in
        1)
            echo -e "  ${MAGENTA}[通常面]${NC}                              ${MAGENTA}[使用文字]${NC}"
            echo "    そ こ し て ょ  │  つ ん い の り ち"
            echo -e "    ${GREEN}は か${NC} ★ ${GREEN}と た${NC}  │  ${GREEN}く う${NC} ★ ${GREEN}゛ き れ${NC}     ${YELLOW}は・か・と・た・く・う・゛・き・れ${NC}"
            echo "    す け に な さ  │  っ る 、 。 ゜ ・     濁音: が・だ・ぐ・ば・ぎ"
            ;;
        2)
            echo -e "  ${MAGENTA}[通常面]${NC}"
            echo -e "    ${GREEN}そ こ し て ょ${NC}  │  ${GREEN}つ ん い の り ち${NC}"
            echo -e "    ${GREEN}は か${NC} ★ ${GREEN}と た${NC}  │  ${GREEN}く う${NC} ★ ${GREEN}゛ き れ${NC}"
            echo "    す け に な さ  │  っ る 、 。 ゜ ・"
            ;;
        3)
            echo -e "  ${MAGENTA}[通常面]${NC}"
            echo -e "    ${GREEN}そ こ し て ょ${NC}  │  ${GREEN}つ ん い の り ち${NC}"
            echo -e "    ${GREEN}は か${NC} ★ ${GREEN}と た${NC}  │  ${GREEN}く う${NC} ★ ${GREEN}゛ き れ${NC}"
            echo -e "    ${GREEN}す け に な さ${NC}  │  ${GREEN}っ る${NC} 、 。 ${GREEN}゜${NC} ・"
            ;;
        4)
            echo -e "  ${MAGENTA}[通常面]${NC}                              ${MAGENTA}[シフト面]${NC}"
            echo -e "    ${GREEN}そ こ し て ょ${NC}  │  ${GREEN}つ ん い の り ち${NC}      ぁ ひ ほ ふ め  │  ぬ え み や ぇ 「"
            echo -e "    ${GREEN}は か${NC} ★ ${GREEN}と た${NC}  │  ${GREEN}く う${NC} ★ ${GREEN}゛ き れ${NC}      ${GREEN}ぃ を ら あ よ${NC}  │  ${GREEN}ま お も わ ゆ${NC} 」"
            echo -e "    ${GREEN}す け に な さ${NC}  │  ${GREEN}っ る${NC} 、 。 ${GREEN}゜${NC} ・      ぅ へ せ ゅ ゃ  │  む ろ ね ー ぉ"
            ;;
        5)
            echo -e "  ${MAGENTA}[通常面]${NC}                              ${MAGENTA}[シフト面]${NC}"
            echo -e "    ${GREEN}そ こ し て ょ${NC}  │  ${GREEN}つ ん い の り ち${NC}      ${GREEN}ぁ ひ ほ ふ め${NC}  │  ${GREEN}ぬ え み や ぇ${NC} 「"
            echo -e "    ${GREEN}は か${NC} ★ ${GREEN}と た${NC}  │  ${GREEN}く う${NC} ★ ${GREEN}゛ き れ${NC}      ${GREEN}ぃ を ら あ よ${NC}  │  ${GREEN}ま お も わ ゆ${NC} 」"
            echo -e "    ${GREEN}す け に な さ${NC}  │  ${GREEN}っ る${NC} 、 。 ${GREEN}゜${NC} ・      ぅ へ せ ゅ ゃ  │  む ろ ね ー ぉ"
            ;;
        6)
            echo -e "  ${MAGENTA}[通常面]${NC}                              ${MAGENTA}[シフト面]${NC}"
            echo -e "    ${GREEN}そ こ し て ょ${NC}  │  ${GREEN}つ ん い の り ち${NC}      ${GREEN}ぁ ひ ほ ふ め${NC}  │  ${GREEN}ぬ え み や ぇ${NC} 「"
            echo -e "    ${GREEN}は か${NC} ★ ${GREEN}と た${NC}  │  ${GREEN}く う${NC} ★ ${GREEN}゛ き れ${NC}      ${GREEN}ぃ を ら あ よ${NC}  │  ${GREEN}ま お も わ ゆ${NC} 」"
            echo -e "    ${GREEN}す け に な さ${NC}  │  ${GREEN}っ る${NC} 、 。 ${GREEN}゜${NC} ・      ${GREEN}ぅ へ せ ゅ ゃ${NC}  │  ${GREEN}む ろ ね ー ぉ${NC}"
            ;;
    esac
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# メインのタイピングゲーム
play_round() {
    local level=$1
    local words_string=$(get_words_for_level $level)
    local words=($words_string)
    
    # シャッフル
    local shuffled=($(shuffle_array "${words[@]}"))
    
    local correct=0
    local wrong=0
    local char_count=0
    
    # 初期画面描画
    redraw_screen $level 0 0 0 $WORDS_PER_ROUND
    
    echo ""
    echo -e "  ${GREEN}Enterキーを押すとスタート...${NC}"
    read -r
    
    local start_time=$(date +%s)
    
    for ((i = 0; i < WORDS_PER_ROUND && i < ${#shuffled[@]}; i++)); do
        local word_data="${shuffled[$i]}"
        local word="${word_data%%:*}"
        local meaning="${word_data##*:}"
        
        # 毎回画面を再描画（配列を固定表示）
        redraw_screen $level $correct $wrong $((i + 1)) $WORDS_PER_ROUND
        
        echo ""
        echo -e "  お題: ${BOLD}${YELLOW}$word${NC} （$meaning）"
        echo ""
        echo -n "  > "
        
        read -r input
        
        if [ "$input" = "$word" ]; then
            ((correct++))
            char_count=$((char_count + ${#word}))
        else
            # 不正解時は一瞬表示
            redraw_screen $level $correct $((wrong + 1)) $((i + 1)) $WORDS_PER_ROUND
            echo ""
            echo -e "  ${RED}✗ 不正解${NC}  お題: ${YELLOW}$word${NC}  入力: ${RED}$input${NC}"
            echo ""
            echo -e "  ${CYAN}Enterで次へ...${NC}"
            read -r
            ((wrong++))
        fi
    done
    
    local end_time=$(date +%s)
    local time_taken=$((end_time - start_time))
    
    local wpm=0
    if [ $time_taken -gt 0 ]; then
        wpm=$((char_count * 60 / time_taken))
    fi
    
    # 結果画面
    clear
    show_round_result $correct $wrong $time_taken $wpm
    
    total_correct=$((total_correct + correct))
    total_wrong=$((total_wrong + wrong))
    
    return $correct
}

# メニュー
show_menu() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━ メニュー ━━━━━━━━━━${NC}"
    echo "  1) 同じレベルをもう一度"
    echo "  2) 次のレベルへ進む"
    echo "  3) レベルを選び直す"
    echo "  4) 終了"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -n "  選択 (1-4): "
}

# メイン処理
main() {
    show_title
    read -r current_level
    
    # 入力チェック
    if ! [[ "$current_level" =~ ^[1-6]$ ]]; then
        current_level=1
    fi
    
    while true; do
        play_round $current_level
        
        show_menu
        read -r choice
        
        case $choice in
            1)
                # 同じレベルをもう一度
                ;;
            2)
                # 次のレベルへ
                if [ $current_level -lt 6 ]; then
                    ((current_level++))
                    echo -e "${GREEN}レベル $current_level に進みます！${NC}"
                    sleep 1
                else
                    echo -e "${YELLOW}最高レベルに到達しています！${NC}"
                    sleep 1
                fi
                ;;
            3)
                # レベル選択
                echo -n "  レベルを入力 (1-6): "
                read -r new_level
                if [[ "$new_level" =~ ^[1-6]$ ]]; then
                    current_level=$new_level
                fi
                ;;
            4)
                # 終了
                show_final_result
                echo -e "${CYAN}お疲れ様でした！また練習しましょう！${NC}"
                exit 0
                ;;
            *)
                ;;
        esac
    done
}

# 実行
main
