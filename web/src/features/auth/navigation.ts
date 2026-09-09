/** 认证跳转目标校验；value是URL中的不可信next参数。 */
export function safeReturnPath(value: string | null): string {
  if (!value || value.length > 500 || !/^\/app(?:\/[A-Za-z0-9_-]+)*$/.test(value)) return '/app';
  return value;
}
