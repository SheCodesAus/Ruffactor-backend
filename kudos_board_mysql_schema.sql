-- MySQL 8+ schema aligned with the current Django backend.
-- DrawSQL-friendly: complete table references and clean FK definitions.
--
-- IMPORTANT:
-- - `accounts_user` below is a simplified structure for schema visualization/import.
-- - In a real Django database, auth tables are managed by Django migrations.

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS accounts_kudostargetteam;
DROP TABLE IF EXISTS accounts_kudosskilltag;
DROP TABLE IF EXISTS accounts_kudos;
DROP TABLE IF EXISTS accounts_teammembership;
DROP TABLE IF EXISTS accounts_team;
DROP TABLE IF EXISTS accounts_skillcategory;
DROP TABLE IF EXISTS accounts_profile;
DROP TABLE IF EXISTS accounts_user;

-- Project user model (simplified for ERD import)
CREATE TABLE accounts_user (
  id         INT NOT NULL AUTO_INCREMENT,
  email      VARCHAR(254) NOT NULL,
  first_name VARCHAR(150) NOT NULL,
  last_name  VARCHAR(150) NOT NULL,
  password   VARCHAR(128) NOT NULL,
  is_staff   TINYINT(1) NOT NULL DEFAULT 0,
  is_active  TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (id),
  UNIQUE KEY uq_accounts_user_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE accounts_profile (
  id           BIGINT NOT NULL AUTO_INCREMENT,
  created_at   DATETIME(6) NOT NULL,
  updated_at   DATETIME(6) NOT NULL,
  display_name VARCHAR(120) NOT NULL DEFAULT '',
  bio          LONGTEXT NOT NULL,
  avatar_url   VARCHAR(200) NOT NULL DEFAULT '',
  user_id      INT NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_accounts_profile_user (user_id),
  CONSTRAINT fk_accounts_profile_user
    FOREIGN KEY (user_id) REFERENCES accounts_user(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE accounts_skillcategory (
  id          BIGINT NOT NULL AUTO_INCREMENT,
  created_at  DATETIME(6) NOT NULL,
  updated_at  DATETIME(6) NOT NULL,
  name        VARCHAR(80) NOT NULL,
  slug        VARCHAR(90) NOT NULL,
  description LONGTEXT NOT NULL,
  is_active   TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (id),
  UNIQUE KEY uq_accounts_skillcategory_name (name),
  UNIQUE KEY uq_accounts_skillcategory_slug (slug)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE accounts_team (
  id          BIGINT NOT NULL AUTO_INCREMENT,
  created_at  DATETIME(6) NOT NULL,
  updated_at  DATETIME(6) NOT NULL,
  name        VARCHAR(120) NOT NULL,
  slug        VARCHAR(140) NOT NULL,
  description LONGTEXT NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_accounts_team_name (name),
  UNIQUE KEY uq_accounts_team_slug (slug)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE accounts_teammembership (
  id         BIGINT NOT NULL AUTO_INCREMENT,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  role       VARCHAR(10) NOT NULL DEFAULT 'member',
  team_id    BIGINT NOT NULL,
  user_id    INT NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_accounts_teammembership_team_user (team_id, user_id),
  KEY idx_accounts_teammembership_team_role (team_id, role),
  KEY idx_accounts_teammembership_user_role (user_id, role),
  CONSTRAINT fk_accounts_teammembership_team
    FOREIGN KEY (team_id) REFERENCES accounts_team(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_accounts_teammembership_user
    FOREIGN KEY (user_id) REFERENCES accounts_user(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE accounts_kudos (
  id           BIGINT NOT NULL AUTO_INCREMENT,
  created_at   DATETIME(6) NOT NULL,
  updated_at   DATETIME(6) NOT NULL,
  message      LONGTEXT NOT NULL,
  link_url     VARCHAR(200) NOT NULL DEFAULT '',
  media_url    VARCHAR(200) NOT NULL DEFAULT '',
  visibility   VARCHAR(10) NOT NULL DEFAULT 'public',
  recipient_id INT NOT NULL,
  sender_id    INT NOT NULL,
  PRIMARY KEY (id),
  KEY idx_accounts_kudos_created_at (created_at),
  KEY idx_accounts_kudos_recipient_created_at (recipient_id, created_at),
  KEY idx_accounts_kudos_sender_created_at (sender_id, created_at),
  KEY idx_accounts_kudos_visibility_created_at (visibility, created_at),
  CONSTRAINT fk_accounts_kudos_recipient
    FOREIGN KEY (recipient_id) REFERENCES accounts_user(id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_accounts_kudos_sender
    FOREIGN KEY (sender_id) REFERENCES accounts_user(id)
    ON DELETE RESTRICT,
  CONSTRAINT chk_accounts_kudos_not_self CHECK (sender_id <> recipient_id),
  CONSTRAINT chk_accounts_kudos_visibility CHECK (visibility IN ('public', 'team', 'private'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE accounts_kudosskilltag (
  id         BIGINT NOT NULL AUTO_INCREMENT,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  kudos_id   BIGINT NOT NULL,
  skill_id   BIGINT NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_accounts_kudosskilltag_kudos_skill (kudos_id, skill_id),
  KEY idx_accounts_kudosskilltag_skill_created_at (skill_id, created_at),
  KEY idx_accounts_kudosskilltag_kudos_created_at (kudos_id, created_at),
  CONSTRAINT fk_accounts_kudosskilltag_kudos
    FOREIGN KEY (kudos_id) REFERENCES accounts_kudos(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_accounts_kudosskilltag_skill
    FOREIGN KEY (skill_id) REFERENCES accounts_skillcategory(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE accounts_kudostargetteam (
  id         BIGINT NOT NULL AUTO_INCREMENT,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  kudos_id   BIGINT NOT NULL,
  team_id    BIGINT NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_accounts_kudostargetteam_kudos_team (kudos_id, team_id),
  KEY idx_accounts_kudostargetteam_team_created_at (team_id, created_at),
  KEY idx_accounts_kudostargetteam_kudos_created_at (kudos_id, created_at),
  CONSTRAINT fk_accounts_kudostargetteam_kudos
    FOREIGN KEY (kudos_id) REFERENCES accounts_kudos(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_accounts_kudostargetteam_team
    FOREIGN KEY (team_id) REFERENCES accounts_team(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS = 1;
