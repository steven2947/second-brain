/** 使用真实 Vite 配置验证文件白名单；不启动服务、不读取私有文件。 */
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it } from 'vitest';
import { isFileServingAllowed, resolveConfig, type ResolvedConfig } from 'vite';

describe('开发文件边界', () => {
  let config: ResolvedConfig;
  beforeAll(async () => {
    config = await resolveConfig({
      configFile: fileURLToPath(new URL('../vite.config.ts', import.meta.url)),
    }, 'serve');
  });

  it('允许中文路径下的 web 文件，不依赖模块自动白名单', () => {
    for (const relative of ['../package.json', './main.tsx']) {
      const path = fileURLToPath(new URL(relative, import.meta.url));
      expect(isFileServingAllowed(config, path)).toBe(true);
    }
  });

  it('拒绝 web 外的运行配置、提示词和旧核心文件', () => {
    for (const relative of [
      '../../.runtime/product.env',
      '../../prompts/answer-orchestrator.v3.md',
      '../../src/orchestration/intake.py',
    ]) {
      const path = fileURLToPath(new URL(relative, import.meta.url));
      expect(isFileServingAllowed(config, path)).toBe(false);
    }
  });
});
