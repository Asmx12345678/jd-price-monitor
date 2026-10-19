# 京东联盟接口申请清单

申请入口：<https://union.jd.com/openplatform/groupApply>

如果权限组页面没有目标接口，工单入口：<https://union.jd.com/openplatform/workOrderList/createWorkOrder>

## 本项目需要申请的接口

1. `jd.union.open.goods.query`：按关键词、类目和 SKU 扩展全站商品池。
2. `jd.union.open.coupon.query`：校验公开优惠券门槛、状态和有效期。
3. `jd.union.open.promotion.intelligence.query`：发现官方公开优惠线报与优惠玩法。
4. `jd.union.open.goods.combination.query`：获取公开券和活动对应的凑单商品组合。

本项目是自有媒体使用，不申请工具服务商专用的
`jd.union.open.promotion.tools.intelligence.query`，除非账号以后升级为工具服务商。

## 可直接粘贴的申请说明

> 我们正在开发一个自有、只读的京东商品优惠监控工具。系统定时查询京东官方联盟数据，记录商品公开价格、公开优惠券和活动信息，在价格或单位价格明显下降时展示京东商品链接。系统不提供购物车、代下单、支付、账号共享或 AppKey 转租，不抓取用户隐私数据。申请商品查询、优惠券查询、官方优惠线报及商品组合接口，用于扩大真实商品覆盖，并准确展示公开优惠的门槛、有效期和凑单方式。

## 推广位

在京东联盟的推广管理中创建一个用于本监控工具的推广位。导购媒体列表中的“媒体ID”是
`siteId`，推广位列表中的“推广位ID”是 `positionId`。两者都写入本机 `.env`：

```env
JD_SITE_ID=这里填写导购媒体ID
JD_POSITION_ID=这里填写推广位ID
```

不要把 AppKey、SecretKey 或登录 Cookie 放进申请说明、截图或工单附件。

## 仍无法通过联盟接口获得的数据

- 某个账号的 PLUS、店铺会员或定向优惠；
- 用户自己的京豆、红包余额；
- 白条、银行卡等支付方式优惠；
- 地区、收货地址、账户风控造成的结算差异；
- 下单后退款产生的商品分摊结果。

这些数据只能在对应用户登录后的购物车或结算页面确认，不能把公开联盟价标记为该用户的最终付款价。
