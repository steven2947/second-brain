# interfaces

cli.py 暴露五项查询、analyze/validate-analysis 可审计调用，以及 prepare/assemble/complete/validate/publish/bundle/author-skill/package；`merge-candidates` 只合并已经验证的单书候选，不读取或发布原书。delivery.py 负责白名单打包。MCP、HTTP 和网页尚未实现。
