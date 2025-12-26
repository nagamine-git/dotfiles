#!/bin/bash

# ============================================
# 月配列2-263 タイピング練習ゲーム v2
# 頻度順に1文字ずつ習得
# ============================================

# 色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
GRAY='\033[0;90m'
WHITE='\033[1;37m'
NC='\033[0m'
BOLD='\033[1m'

# 文字リスト（最初の5文字はホームポジション：は・か・と・う・き）
CHAR_ORDER=(
    は か と う き
    の に た い を る が し で て
    な っ れ ら も す り こ だ ま
    さ め く あ け ど ん え よ つ
    や そ わ ち み せ ろ ば お じ
    べ ず げ ほ へ び む ご ね ぶ
    ぐ ぎ ひ ょ づ ぼ ざ ふ ゃ ぞ
    ゆ ぜ ぬ ぱ ゅ ぴ ぽ ぷ ぺ ぁ
    ぇ ぢ ゑ ゐ ぉ ぃ ゎ ぅ
)

# 設定
SAVE_FILE="$HOME/.tsuki_typing_save"
ROUND_SIZE=10
UNLOCK_THRESHOLD=60

# 状態
declare -A CHAR_MASTERY
unlocked_chars=5

# 単語データベース（ひらがな:意味）
WORDS=(
    # は・か・と・う・き のみ
    "かう:買う"
    "とう:問う"
    "はく:履く"
    "かく:書く"
    "きく:聞く"
    "たく:炊く"
    "かた:型"
    "たか:鷹"
    "うた:歌"
    "きた:北"
    "いき:息"
    "かき:柿"
    "たき:滝"
    "うき:浮き"
    "はか:墓"
    "かと:蚊と"
    "とか:とか"
    "きかい:機会"
    # 基本単語
    "の:の"
    "に:に"
    "た:た"
    "たい:鯛"
    "ない:無い"
    "いた:板"
    "には:庭"
    "のに:のに"
    "たに:谷"
    "にた:似た"
    "いに:往に"
    "はい:灰"
    "はた:旗"
    "はな:花"
    "いは:岩"
    "をい:甥"
    "とい:問い"
    "いと:糸"
    "とは:とは"
    "との:との"
    "とに:とに"
    "たと:たと"
    "るい:類"
    "とる:取る"
    "いる:居る"
    "はる:春"
    "なる:成る"
    "のる:乗る"
    "たる:樽"
    "がい:害"
    "がた:型"
    "しる:知る"
    "しに:死に"
    "しな:品"
    "しの:篠"
    "いし:石"
    "にし:西"
    "はし:橋"
    "でる:出る"
    "では:では"
    "いで:出で"
    "てる:照る"
    "して:して"
    "なに:何"
    "なの:なの"
    "なが:長"
    "かい:貝"
    "かた:型"
    "たか:鷹"
    "かな:仮名"
    "かに:蟹"
    "いか:烏賊"
    "しか:鹿"
    "っと:っと"
    "かった:勝った"
    "いった:行った"
    "なった:成った"
    "れい:礼"
    "かれ:彼"
    "たれ:誰"
    "これ:これ"
    "それ:それ"
    "られ:られ"
    "らい:来"
    "から:空"
    "なら:奈良"
    "しら:白"
    "もの:物"
    "もち:餅"
    "もり:森"
    "いも:芋"
    "うた:歌"
    "うに:雲丹"
    "うし:牛"
    "かう:買う"
    "いう:言う"
    "すい:粋"
    "すな:砂"
    "するな:するな"
    "ます:鱒"
    "りく:陸"
    "のり:海苔"
    "しり:尻"
    "とり:鳥"
    "くり:栗"
    "こい:鯉"
    "ここ:此処"
    "こと:事"
    "この:この"
    "だい:台"
    "だれ:誰"
    "まい:舞"
    "まち:町"
    "いま:今"
    "くま:熊"
    "さい:才"
    "さる:猿"
    "さか:坂"
    "あさ:朝"
    "きた:北"
    "きり:霧"
    "かき:柿"
    "いき:息"
    "すき:好き"
    "めい:姪"
    "あめ:雨"
    "くち:口"
    "くも:雲"
    "くに:国"
    "あい:愛"
    "あか:赤"
    "あき:秋"
    "ある:有る"
    "けい:刑"
    "たけ:竹"
    "さけ:酒"
    "いけ:池"
    "どこ:何処"
    "どれ:どれ"
    "まど:窓"
    "かど:角"
    "んと:んと"
    "うんと:うんと"
    "えき:駅"
    "かえる:帰る"
    "まえ:前"
    "うえ:上"
    "よい:良い"
    "よる:夜"
    "およぐ:泳ぐ"
    "つき:月"
    "つく:付く"
    "いつ:何時"
    "やま:山"
    "やる:遣る"
    "いや:嫌"
    "そこ:底"
    "その:その"
    "そう:然う"
    "わに:鰐"
    "かわ:川"
    "にわ:庭"
    "ちり:塵"
    "まち:町"
    "みち:道"
    "かち:勝ち"
    "みる:見る"
    "みみ:耳"
    "うみ:海"
    "せい:背"
    "せかい:世界"
    "ろく:六"
    "しろ:白"
    "ばい:倍"
    "ばか:馬鹿"
    "おい:甥"
    "おか:丘"
    "おと:音"
    "じる:汁"
    "かじ:舵"
    "べつ:別"
    "ずる:狡"
    "げた:下駄"
    "ほし:星"
    "ほか:他"
    "へた:下手"
    "へや:部屋"
    "びる:びる"
    "むし:虫"
    "むら:村"
    "むく:剥く"
    "ごい:語彙"
    "ねこ:猫"
    "ねる:寝る"
    "かね:金"
    "ぶた:豚"
    "ぐち:愚痴"
    "ぎり:義理"
    "ひる:昼"
    "ひと:人"
    "ひかり:光"
    "きょう:今日"
    "りょう:量"
    "ぼく:僕"
    "ざる:猿"
    "ふく:服"
    "ふね:船"
    "ふゆ:冬"
    "しゃく:癪"
    "ぞう:象"
    "ゆき:雪"
    "ゆめ:夢"
    "ぜに:銭"
    "ぬの:布"
    "ぱい:杯"
    "しゅう:週"
    "ぴか:ぴか"
    "ぽい:ぽい"
    "ぷう:ぷう"
    "ぺた:ぺた"
    "ありがとう:有難う"
    "おはよう:お早う"
    "こんにちは:今日は"
    "さようなら:左様なら"
    "おもしろい:面白い"
    "たのしい:楽しい"
    "うつくしい:美しい"
    "あたらしい:新しい"
    "むずかしい:難しい"
    "やさしい:優しい"
    "かわいい:可愛い"
    "おいしい:美味しい"
    "すばらしい:素晴らしい"
    "ともだち:友達"
    "せんせい:先生"
    "がっこう:学校"
    "びょういん:病院"
    "としょかん:図書館"
    "でんしゃ:電車"
    "ひこうき:飛行機"
    "しんかんせん:新幹線"
    "にほん:日本"
    "とうきょう:東京"
    "おおさか:大阪"
    "きょうと:京都"
    "ほっかいどう:北海道"
    "おきなわ:沖縄"
    "たべる:食べる"
    "のむ:飲む"
    "はなす:話す"
    "きく:聞く"
    "よむ:読む"
    "かく:書く"
    "あるく:歩く"
    "はしる:走る"
    "つくる:作る"
    "おしえる:教える"
    "わかる:分かる"
    "おぼえる:覚える"
    "わすれる:忘れる"
    "はじめる:始める"
    "おわる:終わる"
    "やすむ:休む"
    "はたらく:働く"
    "あそぶ:遊ぶ"
    "うたう:歌う"
    "わらう:笑う"
    "なく:泣く"
)

# 保存
save_progress() {
    {
        echo "unlocked=$unlocked_chars"
        for i in "${!CHAR_ORDER[@]}"; do
            local char="${CHAR_ORDER[$i]}"
            echo "m$i=${CHAR_MASTERY[$char]:-0}"
        done
    } > "$SAVE_FILE"
}

# 読み込み
load_progress() {
    for char in "${CHAR_ORDER[@]}"; do
        CHAR_MASTERY[$char]=0
    done
    
    if [ -f "$SAVE_FILE" ]; then
        source "$SAVE_FILE"
        for i in "${!CHAR_ORDER[@]}"; do
            local char="${CHAR_ORDER[$i]}"
            eval "CHAR_MASTERY[$char]=\${m$i:-0}"
        done
    fi
}

# 習熟度の色
mastery_color() {
    local m=$1
    if [ "$m" -ge 80 ]; then echo "${GREEN}"
    elif [ "$m" -ge 60 ]; then echo "${YELLOW}"
    elif [ "$m" -ge 40 ]; then echo "${MAGENTA}"
    elif [ "$m" -ge 1 ]; then echo "${RED}"
    else echo "${GRAY}"
    fi
}

# 習熟度バー表示
show_mastery_bar() {
    echo -ne "  "
    for i in "${!CHAR_ORDER[@]}"; do
        local char="${CHAR_ORDER[$i]}"
        if [ "$i" -lt "$unlocked_chars" ]; then
            local m=${CHAR_MASTERY[$char]:-0}
            echo -ne "$(mastery_color $m)${char}${NC} "
        else
            echo -ne "${GRAY}□${NC} "
        fi
        [ $(( (i + 1) % 20 )) -eq 0 ] && echo -e "\n  "
    done
    echo ""
}

# 配列プレビュー
show_layout() {
    local avail=""
    for ((i=0; i<unlocked_chars; i++)); do
        avail+="${CHAR_ORDER[$i]}"
    done
    
    print_key() {
        local c=$1
        if [[ "$avail" == *"$c"* ]]; then
            local m=${CHAR_MASTERY[$c]:-0}
            echo -ne "$(mastery_color $m)$c${NC} "
        else
            echo -ne "${GRAY}□${NC} "
        fi
    }
    
    echo -e "  ${CYAN}[通常面]${NC}                            ${CYAN}[シフト面]${NC}"
    
    # 上段
    echo -n "   "
    for c in そ こ し て ょ; do print_key "$c"; done
    echo -n "│ "
    for c in つ ん い の り ち; do print_key "$c"; done
    echo -n "    "
    for c in ぁ ひ ほ ふ め; do print_key "$c"; done
    echo -n "│ "
    for c in ぬ え み や ぇ; do print_key "$c"; done
    echo ""
    
    # 中段
    echo -n "   "
    for c in は か; do print_key "$c"; done
    echo -ne "${WHITE}★${NC} "
    for c in と た; do print_key "$c"; done
    echo -n "│ "
    for c in く う; do print_key "$c"; done
    echo -ne "${WHITE}★${NC} "
    for c in ゛ き れ; do print_key "$c"; done
    echo -n "    "
    for c in ぃ を ら あ よ; do print_key "$c"; done
    echo -n "│ "
    for c in ま お も わ ゆ; do print_key "$c"; done
    echo ""
    
    # 下段
    echo -n "   "
    for c in す け に な さ; do print_key "$c"; done
    echo -n "│ "
    for c in っ る; do print_key "$c"; done
    echo -ne "${GRAY}、 。 ゜${NC} "
    echo -n "    "
    for c in ぅ へ せ ゅ ゃ; do print_key "$c"; done
    echo -n "│ "
    for c in む ろ ね ー ぉ; do print_key "$c"; done
    echo ""
}

# 画面描画
draw_screen() {
    local correct=$1 wrong=$2 qnum=$3 total=$4
    clear
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}月配列タイピング${NC} │ 文字:${CYAN}$unlocked_chars/${#CHAR_ORDER[@]}${NC} │ 正解:${GREEN}$correct${NC} ミス:${RED}$wrong${NC} │ $qnum/$total"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    show_layout
    echo -e "${CYAN}───────────────────────────────────────────────────────────────────────────${NC}"
    show_mastery_bar
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# 使用可能な文字を取得
get_available() {
    local result=""
    for ((i=0; i<unlocked_chars && i<${#CHAR_ORDER[@]}; i++)); do
        result+="${CHAR_ORDER[$i]}"
    done
    echo "$result"
}

# 単語が使えるかチェック
word_ok() {
    local word=$1 avail=$2
    for ((i=0; i<${#word}; i++)); do
        [[ "$avail" != *"${word:$i:1}"* ]] && return 1
    done
    return 0
}

# 使える単語を取得
get_words() {
    local avail=$(get_available)
    local result=()
    for entry in "${WORDS[@]}"; do
        local word="${entry%%:*}"
        word_ok "$word" "$avail" && result+=("$entry")
    done
    echo "${result[@]}"
}

# 習熟度更新
update_mastery() {
    local word=$1 correct=$2
    for ((i=0; i<${#word}; i++)); do
        local c="${word:$i:1}"
        local m=${CHAR_MASTERY[$c]:-0}
        if [ "$correct" -eq 1 ]; then
            m=$((m + 10))
            [ $m -gt 100 ] && m=100
        else
            m=$((m - 15))
            [ $m -lt 0 ] && m=0
        fi
        CHAR_MASTERY[$c]=$m
    done
}

# アンロックチェック
check_unlock() {
    [ "$unlocked_chars" -ge "${#CHAR_ORDER[@]}" ] && return
    
    local total=0
    for ((i=0; i<unlocked_chars; i++)); do
        total=$((total + ${CHAR_MASTERY[${CHAR_ORDER[$i]}]:-0}))
    done
    local avg=$((total / unlocked_chars))
    
    if [ $avg -ge $UNLOCK_THRESHOLD ]; then
        ((unlocked_chars++))
        echo -e "\n  ${GREEN}★ 新文字アンロック: ${YELLOW}${CHAR_ORDER[$((unlocked_chars-1))]}${NC}"
        sleep 1
    fi
}

# シャッフル
shuffle() {
    local arr=("$@")
    for ((i=${#arr[@]}-1; i>0; i--)); do
        local j=$((RANDOM % (i+1)))
        local tmp="${arr[$i]}"
        arr[$i]="${arr[$j]}"
        arr[$j]="$tmp"
    done
    echo "${arr[@]}"
}

# ラウンド実行
play_round() {
    local words_str=$(get_words)
    local words=($words_str)
    
    if [ ${#words[@]} -lt 3 ]; then
        echo -e "${YELLOW}単語が少ないです。練習を続けて文字を増やしましょう。${NC}"
        read -r
        return
    fi
    
    local shuffled=($(shuffle "${words[@]}"))
    local size=$ROUND_SIZE
    [ ${#shuffled[@]} -lt $size ] && size=${#shuffled[@]}
    
    local correct=0 wrong=0
    
    draw_screen 0 0 0 $size
    echo -e "\n  ${GREEN}Enter で開始${NC}"
    read -r
    
    for ((q=0; q<size; q++)); do
        local entry="${shuffled[$q]}"
        local word="${entry%%:*}"
        local meaning="${entry##*:}"
        
        draw_screen $correct $wrong $((q+1)) $size
        echo -e "\n  お題: ${BOLD}${YELLOW}$word${NC}（$meaning）\n"
        echo -n "  > "
        read -e -r input
        
        if [ "$input" = "$word" ]; then
            ((correct++))
            update_mastery "$word" 1
        else
            ((wrong++))
            update_mastery "$word" 0
            draw_screen $correct $wrong $((q+1)) $size
            echo -e "\n  ${RED}✗${NC} 正解: ${YELLOW}$word${NC}  入力: ${RED}$input${NC}"
            echo -e "  ${GRAY}Enter で次へ${NC}"
            read -r
        fi
        
        check_unlock
    done
    
    save_progress
    
    # 結果
    draw_screen $correct $wrong $size $size
    echo ""
    echo -e "  ${BOLD}結果${NC}: 正解 ${GREEN}$correct${NC} / ミス ${RED}$wrong${NC}"
    [ $((correct+wrong)) -gt 0 ] && echo -e "  正解率: ${CYAN}$((correct*100/(correct+wrong)))%${NC}"
}

# メイン
main() {
    load_progress
    
    while true; do
        play_round
        
        echo ""
        echo -e "  ${CYAN}1)続ける 2)リセット 3)終了${NC}"
        echo -n "  > "
        read -r choice
        
        case $choice in
            2)
                echo -n "  リセット? (y/n): "
                read -r yn
                [ "$yn" = "y" ] && rm -f "$SAVE_FILE" && unlocked_chars=5 && load_progress
                ;;
            3)
                save_progress
                echo -e "  ${CYAN}お疲れ様！${NC}"
                exit 0
                ;;
        esac
    done
}

main
