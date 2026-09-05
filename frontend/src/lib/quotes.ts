/** 今日签文案与当天选择逻辑：用户换出的内容会保留到当天结束。 */
const QUOTES: { text: string; emoji: string }[] = [
  { text: '你现在翻的书，以后都是数不完的钱。', emoji: '📖' },
  { text: '刷题一时爽，一直刷题一直爽。', emoji: '✏️' },
  { text: '别人还在犹豫，你已经做完三道题。', emoji: '⚡' },
  { text: '今天的错题，是明天的分数。', emoji: '🎯' },
  { text: '没有白走的路，每一步都算数。', emoji: '🛤️' },
  { text: '你只管努力，剩下的交给时间。', emoji: '⏳' },
  { text: '题是做不完的，但方法是学得会的。', emoji: '🧭' },
  { text: '耐得住寂寞，才守得住繁华。', emoji: '🌙' },
  { text: '现在流的汗，是考场上握笔的稳。', emoji: '💪' },
  { text: '把不会的弄会，就是最快的进步。', emoji: '🔑' },
  { text: '别慌，月亮也正在大海某处迷茫。', emoji: '🌊' },
  { text: '题目虐我千百遍，我待题目如初恋。', emoji: '💘' },
  { text: '你以为的极限，只是别人的起点。', emoji: '🚀' },
  { text: '早起的鸟儿有虫吃，早起的你绩点高。', emoji: '🌅' },
  { text: '凡事预则立，不预则废。', emoji: '📋' },
  { text: '慢慢来，比较快。', emoji: '🐢' },
  { text: '量变引起质变，坚持就是胜利。', emoji: '📈' },
  { text: '行胜于言，做就完了。', emoji: '🛠️' },
  { text: '今日事，今日毕。', emoji: '✅' },
  { text: '书山有路勤为径，学海无涯乐作舟。', emoji: '⛰️' },
  { text: '你的对手在看书，你的仇人在刷题。', emoji: '⚔️' },
  { text: '乾坤未定，你我皆是黑马。', emoji: '🐎' },
  { text: '星光不问赶路人，时光不负有心人。', emoji: '✨' },
  { text: '所有偷过的懒，都会变成打脸的巴掌。', emoji: '👋' },
  { text: '越努力，越幸运。', emoji: '🍀' },
  { text: '愿你合上笔盖的那一刻，有战士收刀入鞘的骄傲。', emoji: '🗡️' },
  { text: '分数不会陪你演戏，功夫都在平时。', emoji: '🎭' },
  { text: '别人睡觉你学习，这就是差距的开始。', emoji: '⏰' },
  { text: '世界上没有白费的功夫，只有不肯下的功夫。', emoji: '🔨' },
  { text: '复杂的事情简单做，简单的事情重复做。', emoji: '🔁' },
  { text: '会当凌绝顶，一览众山小。', emoji: '🏔️' },
  { text: '锲而不舍，金石可镂。', emoji: '💎' },
  { text: '学如逆水行舟，不进则退。', emoji: '🛶' },
  { text: '路虽远行则将至，事虽难做则必成。', emoji: '🛤️' },
  { text: '博观而约取，厚积而薄发。', emoji: '📚' },
  { text: '不怕慢，就怕站。', emoji: '🚶' },
  { text: '每天进步一点点，期末惊艳所有人。', emoji: '🌟' },
  { text: '错题本越厚，期末心越稳。', emoji: '📒' },
  { text: '但行好事，莫问前程。', emoji: '🙏' },
  { text: '少年不惧岁月长，彼方尚有荣光在。', emoji: '🌄' },
]

export type Quote = (typeof QUOTES)[number]
const QUOTE_STORAGE_KEY = 'hangyou:daily-quote'
function storageKeyForToday(): string { return new Date().toISOString().slice(0, 10) }
export function todayQuote(): Quote { const now = new Date(); return QUOTES[Math.floor(now.getTime() / 86400000) % QUOTES.length] }
export function currentQuote(): Quote {
  try { const saved = JSON.parse(localStorage.getItem(QUOTE_STORAGE_KEY) ?? 'null') as { date: string; index: number } | null; if (saved?.date === storageKeyForToday() && QUOTES[saved.index]) return QUOTES[saved.index] } catch { /* 忽略不可用的本地存储 */ }
  return todayQuote()
}
export function nextQuote(current: Quote): Quote {
  const candidates = QUOTES.filter((_, index) => index !== QUOTES.indexOf(current))
  const next = candidates[Math.floor(Math.random() * candidates.length)] ?? todayQuote()
  try { localStorage.setItem(QUOTE_STORAGE_KEY, JSON.stringify({ date: storageKeyForToday(), index: QUOTES.indexOf(next) })) } catch { /* 隐私模式下仅本次生效 */ }
  return next
}
