-- 啟用 zhparser 擴充
CREATE EXTENSION IF NOT EXISTS zhparser;

-- 建立中文文本搜尋設定
CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);

-- 加入詞性映射（依規格書 11.2）
ALTER TEXT SEARCH CONFIGURATION chinese
    ADD MAPPING FOR n,v,a,i,e,l WITH simple;
