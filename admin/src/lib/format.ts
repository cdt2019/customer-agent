/** token 数写短：3.8k、1.23M。 */
export function tokens(n: number): string {
  if (n >= 1_000_000) return `${+(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${+(n / 1_000).toFixed(1)}k`;
  return String(n);
}

/** 今天的只写时分，别的日子写月-日 时:分。 */
export function when(iso: string): string {
  const at = new Date(iso);
  const hm = at.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  if (at.toDateString() === new Date().toDateString()) return hm;
  return `${String(at.getMonth() + 1).padStart(2, "0")}-${String(at.getDate()).padStart(2, "0")} ${hm}`;
}

/** 钱写到分；不到一分写到厘。 */
export function yuan(n: number): string {
  return `¥${n > 0 && n < 0.01 ? n.toFixed(3) : n.toFixed(2)}`;
}

/** 离现在多久：刚刚、3 分钟前、2 小时前、5 天前。 */
export function ago(iso: string): string {
  const minutes = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)} 小时前`;
  return `${Math.floor(minutes / (24 * 60))} 天前`;
}
