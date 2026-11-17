-- Intelligent Helmet - MariaDB schema

-- 1. Database
CREATE DATABASE IF NOT EXISTS Projet_casque;
USE Projet_casque;

-- 2. Base tables (no foreign keys)
CREATE TABLE utilisateur (
    IdentifiantUtilisateur INT AUTO_INCREMENT PRIMARY KEY,
    Nom VARCHAR(50),
    Prenom VARCHAR(50),
    TypeSanguin VARCHAR(5),
    Allergies TEXT,
    ContactUrgence VARCHAR(20)
);

CREATE TABLE contactsecours (
    IdSecours VARCHAR(50) PRIMARY KEY,
    Contact VARCHAR(50)
);

-- 3. Level 1 tables (one foreign key)
CREATE TABLE lieux (
    IdLieu VARCHAR(50) PRIMARY KEY,
    IdSecours VARCHAR(50),
    Region VARCHAR(100),
    TypeSport VARCHAR(50),
    Latitude DECIMAL(10, 6),
    Longitude DECIMAL(10, 6),
    FOREIGN KEY (IdSecours) REFERENCES contactsecours(IdSecours)
);

CREATE TABLE casque (
    IdentifiantCasque VARCHAR(50) PRIMARY KEY,  -- must match the TTN device ID
    IdCapteurLuminosite INT,
    IdCentraleInertielle INT,
    IdFlexiForce INT,
    IdentifiantUtilisateur INT,
    FOREIGN KEY (IdentifiantUtilisateur) REFERENCES utilisateur(IdentifiantUtilisateur)
);

-- 4. Central table linking user, helmet and location
CREATE TABLE sessions (
    IdSession INT AUTO_INCREMENT PRIMARY KEY,
    DateDebut DATETIME,
    DateFin DATETIME,
    IdentifiantUtilisateur INT,
    IdentifiantCasque VARCHAR(50),
    IdLieu VARCHAR(50),
    FOREIGN KEY (IdentifiantUtilisateur) REFERENCES utilisateur(IdentifiantUtilisateur),
    FOREIGN KEY (IdentifiantCasque) REFERENCES casque(IdentifiantCasque),
    FOREIGN KEY (IdLieu) REFERENCES lieux(IdLieu)
);

-- 5. Time series tables (telemetry)
CREATE TABLE alerte (
    IdentifiantAlerte INT AUTO_INCREMENT PRIMARY KEY,
    HeureAlerte DATETIME,
    latitude DECIMAL(10, 6),
    longitude DECIMAL(10, 6),
    IdSession INT,
    TypeAlerte VARCHAR(50),
    FOREIGN KEY (IdSession) REFERENCES sessions(IdSession)
);

CREATE TABLE infotrajet (
    Identifianttrajet INT AUTO_INCREMENT PRIMARY KEY,
    DateHeureMesure DATETIME,
    latitude DECIMAL(10, 6),
    longitude DECIMAL(10, 6),
    MesureVitesse FLOAT,
    IdSession INT,
    FOREIGN KEY (IdSession) REFERENCES sessions(IdSession)
);
