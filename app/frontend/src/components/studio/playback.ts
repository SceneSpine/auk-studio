/**
 * 全局播放协调（02-UI-UX设计规范 §4.5）：
 * - 一次只播放一个音源：播放时广播 "auk:pause-others"，其余播放器自行暂停。
 * - Space 快捷键作用于「当前活动播放器」（最近播放/挂载的播放器）。
 * WavePlayer / ABPlayer / SampleAudio 共用此模块。
 */

export interface PlayerHandle {
  toggle: () => void;
  pause: () => void;
}

const PAUSE_OTHERS = "auk:pause-others";

let active: PlayerHandle | null = null;

/** 成为 Space 快捷键的目标播放器 */
export function claimActive(handle: PlayerHandle): void {
  active = handle;
}

/** 仅当自己仍是活动播放器时释放（组件卸载时调用） */
export function releaseActive(handle: PlayerHandle): void {
  if (active === handle) active = null;
}

/** 若尚无活动播放器，则认领（首个挂载的播放器兜底） */
export function claimActiveIfNone(handle: PlayerHandle): void {
  if (!active) active = handle;
}

export function toggleActive(): void {
  active?.toggle();
}

/** 广播：除 source 外的所有播放器暂停 */
export function pauseOthers(source: object): void {
  window.dispatchEvent(new CustomEvent(PAUSE_OTHERS, { detail: source }));
}

/** 订阅互斥暂停事件，返回取消订阅函数 */
export function onPauseOthers(cb: (source: object | null) => void): () => void {
  const fn = (e: Event) => cb((e as CustomEvent).detail as object | null);
  window.addEventListener(PAUSE_OTHERS, fn);
  return () => window.removeEventListener(PAUSE_OTHERS, fn);
}

/** 暂停全部播放器 */
export function pauseAll(): void {
  window.dispatchEvent(new CustomEvent(PAUSE_OTHERS, { detail: null }));
}