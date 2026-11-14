/** 任务历史共享小工具（Jobs 列表与详情共用）。 */
import type { Job, JobKind, JobStatus } from "../../types";
import { MODE_LABEL } from "../../types";
import type { StatusTone } from "../ui";

/** 旧后端可能不返回 kind 字段，缺省按推理任务处理（优雅降级）。 */
export function jobKind(j: Job): JobKind {
  return j.kind ?? "infer";
}

export function statusTone(s: JobStatus): StatusTone {
  switch (s) {
    case "completed":
      return "ready";
    case "failed":
      return "error";
    case "cancelled":
      return "unknown";
    case "queued":
      return "neutral";
    default:
      return "progress";
  }
}

/** 表格「模式」列：install/verify 显示任务大类，infer 显示创作模式。 */
export function kindLabel(j: Job): string {
  const k = jobKind(j);
  if (k === "install") return "模型安装";
  if (k === "verify") return "模型校验";
  return MODE_LABEL[j.mode] ?? j.mode;
}

export function modelLabel(v: string | null | undefined): string {
  if (!v) return "—";
  if (v === "flash") return "AuK Flash";
  if (v === "base") return "AuK Base";
  return v;
}

export const INSTALL_PHASE_LABEL: Record<string, string> = {
  prepare: "准备",
  download: "下载",
  verify: "校验",
  convert: "MLX 转换",
  quantize: "8-bit 量化",
  smoke: "冒烟测试",
  done: "完成",
};