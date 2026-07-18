ALTER TABLE app_settings
ADD COLUMN language TEXT NOT NULL DEFAULT 'zh-CN'
CHECK (language IN ('zh-CN', 'en'));
