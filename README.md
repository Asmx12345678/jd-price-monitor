# 京东超市降价雷达

## 价格判定

- `真实历史总价下降`：只比较系统前后两次观测到的同一商品价格。
- `真实历史单位价下降`：只在规格单位可比时比较，例如元/L、元/kg、元/张。
- `公开优惠`：京东联盟当前到手价相对接口参考价的优惠，不再称为历史降价。
- 历史降幅达到 50% 或以上时，必须连续两次观测到相同低价后才展示。
- 卡片会标记高可信、公开券需领取或有条件优惠，并显示最近校验时间。

## Railway 公网部署

生产环境使用 Dockerfile 启动，建议配置持久化卷挂载到 `/data`，并设置：

- `JD_DATABASE_PATH=/data/prices.db`
- `JD_HOST=0.0.0.0`
- `JD_PUBLIC_READ_ONLY=true`
- `JD_MODE=live`
- 京东联盟的 `JD_APP_KEY`、`JD_APP_SECRET`、`JD_SITE_ID`、`JD_POSITION_ID`

`.env` 和本地数据库均已被 Git 与 Docker 排除，不会进入源码仓库或镜像。

一个只在本机运行的商品降价发现工具。它不提供购物车、下单或支付，只负责：

- 扫描 13 个京东联盟精选频道，并默认在 20 页之间自动轮换；
- 同时扫描京东超市、历史低价两个商品素材频道以及公开活动；
- 保存每次价格快照；
- 识别价格下降和券后优惠；
- 按页面设定的间隔自动扫描，并按自定义降幅阈值筛选；
- 尝试解析瓶、罐、袋、重量与容量，计算单位价格；
- 总价不变但包装数量增加时，按历史单位价识别实际降价；
- 仅在重量、容量或相同计数单位之间比较，避免把“包”和“片”直接比较；
- 显示可直接复制的普通京东商品链接。

## 立即预览

```bash
cd jd-price-monitor
python3 app.py
```

打开 <http://127.0.0.1:8765>。首次运行默认为演示模式，不需要京东密钥。

## 接入京东联盟

1. 复制环境变量模板：

   ```bash
   cp .env.example .env
   ```

2. 只在本机编辑 `.env`：

   ```env
   JD_APP_KEY=你的AppKey
   JD_APP_SECRET=你的SecretKey
   JD_SITE_ID=导购媒体ID（可选）
   JD_POSITION_ID=推广位ID（可选）
   JD_MODE=live
   JD_DISCOVERY_PAGES=20
   ```

3. 重新启动 `python3 app.py`。

当前实时采集器使用：

- `jd.union.open.goods.jingfen.query`：京东超市、历史低价、秒杀、自营等优惠池。
- `jd.union.open.goods.material.query`：补充真实商品素材与促销标签。
- `jd.union.open.activity.query`：同步公开活动。

账号还可调用 `jd.union.open.goods.bigfield.query`，后续可继续补充详情字段；
导购媒体ID `JD_SITE_ID` 和推广位ID `JD_POSITION_ID` 是两个不同的数字。
京东实测 `jd.union.open.promotion.common.get` 只支持网站/APP媒体，导购媒体不能使用；
本项目继续使用商品素材接口直接返回的真实京东落地链接。

当前账号没有 `jd.union.open.goods.query` 的关键词全库查询权限，因此扩容采用账号
已授权的真实精选接口：每轮扫描 13 个频道的同一页，下一轮自动切换到下一页，
默认第 20 页后回到第 1 页。所有见过的商品都会留在本地商品池中，覆盖会随运行持续扩大。

接口权限、返回字段和媒体类型会影响实际结果。商品按钮使用京东接口返回的
`materialUrl`，避免把同款主商品号误当成可直接打开的 SKU。

## 自动扫描规则

在首页的“自动监控规则”中设置：

- 降价阈值：例如填写 `50`，只展示降幅达到 50% 的商品；
- 扫描间隔：1 到 1440 分钟。

点击“保存并立即生效”后，规则会写入本地数据库并立刻重新扫描。只要
`python3 app.py` 正在运行，后端就会按设定间隔持续扫描，不需要保持网页打开。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

## 数据位置

价格历史保存在 `data/prices.db`。该目录不会提交到 Git。

