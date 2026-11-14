/** 音色库共享小工具。 */

export const ALLOWED_USE_LABEL: Record<string, string> = {
  personal_research: "个人研究",
  evaluation: "评估",
  non_commercial: "非商业创作",
};

export function allowedUseLabel(v: string | null | undefined): string {
  if (!v) return "未指定";
  return ALLOWED_USE_LABEL[v] ?? v;
}

/** 逗号（中英文）分隔 → 去重去空 chips */
export function parseTags(input: string): string[] {
  const seen = new Set<string>();
  for (const raw of input.split(/[,，]/)) {
    const t = raw.trim();
    if (t) seen.add(t);
  }
  return [...seen];
}

/** 新建音色时的强制授权确认文案（与后端固定 statement 一致） */
export const CONSENT_STATEMENT =
  "我确认对该参考声音拥有合法使用权，仅在本机用于非商业研究/评估用途";