/** 登录回跳仅接受已知同站工作区路径，不传递凭据或任意外部链接。 */
import { describe, expect, it } from 'vitest';
import { safeReturnPath } from './navigation';

describe('登录回跳边界', () => {
  it('缺省进入工作台，允许已有工作区路径', () => {
    expect(safeReturnPath(null)).toBe('/app');
    expect(safeReturnPath('/app/settings')).toBe('/app/settings');
    expect(safeReturnPath('/app/library')).toBe('/app/library');
  });
  it('拒绝外站、协议相对、控制字符、编码逃逸和认证循环', () => {
    for (const value of ['https://evil.test', '//evil.test', '/\\evil.test', '/app/../login', '/app/%2e%2e/login', '/app?token=secret', '/login', '/app\n', '/application', '/app/%2f%2fevil']) {
      expect(safeReturnPath(value)).toBe('/app');
    }
  });
});
