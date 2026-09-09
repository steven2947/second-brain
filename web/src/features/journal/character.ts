/** 读者选择的馆员形象（女生/男生）：仅外观偏好，存localStorage并跨页同步，不含私有数据。 */
import { useEffect, useState } from 'react';

export type Character = 'girl' | 'boy';
const KEY = 'sb-character';

/** 无参数；无记录或读取失败时默认女生版。 */
export function readCharacter(): Character {
  try {
    return localStorage.getItem(KEY) === 'boy' ? 'boy' : 'girl';
  } catch {
    return 'girl';
  }
}

/** 返回当前形象与切换函数；同名偏好事件与storage事件都会同步本页。 */
export function useCharacter(): [Character, (value: Character) => void] {
  const [value, setValue] = useState<Character>(readCharacter);
  useEffect(() => {
    const sync = () => setValue(readCharacter());
    window.addEventListener('sb-character', sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener('sb-character', sync);
      window.removeEventListener('storage', sync);
    };
  }, []);
  const set = (next: Character) => {
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* 存储不可用时仅本次生效 */
    }
    setValue(next);
    window.dispatchEvent(new Event('sb-character'));
  };
  return [value, set];
}

/** base为不带后缀的素材名；返回当前形象对应的图片路径。 */
export function characterImage(base: string, character: Character): string {
  return `/journal/${base}-${character}.png`;
}
