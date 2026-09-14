# 程序设计类课程教辅平台

基于 Django 的在线课程、班级、作业、题库和自主练习平台。

## 环境要求

- Python 3.4+
- Django 1.9.5+

## 配置说明

数据库密码、邮件授权码和 Django Secret Key 均通过环境变量配置，不应提交到代码仓库。

常用环境变量：

- `DJANGO_SECRET_KEY`
- `MYSQL_DATABASE`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_HOST`
- `MYSQL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`

本仓库不包含本地 SQLite 数据库、测试账号、测试答题记录、日志和用户上传文件。
