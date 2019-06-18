#!/bin/env python2

'''
    ccaudio.py - Written by John Hall (john@hall.ws)
    
    Description:
    The purpose behind this script is to provide a crontab-executable
    job that will run, index MP3 files into a database, and perform any
    necessary conversions that are desired.

    Changes:
      - 11/06 - Changed the 'chapter' object from int to str to prevent
		performing calculations on the value when multiple
		chapters are useds (ex: 26-27 = -1). Also added a fix
		for the VERSES tag (was previously VERSE in program but
		has always been VERSES on incoming files).
    
'''

#-----------------------------------------------------------------------
# Begin Imports
#-----------------------------------------------------------------------
import taglib
import logging
import os
import sys
import sqlite3
import hashlib
import time
import random
import smtplib

from email.mime.text import MIMEText

#-----------------------------------------------------------------------
# End Imports
#-----------------------------------------------------------------------

#-----------------------------------------------------------------------
# Begin Settings
#-----------------------------------------------------------------------

# Load our settings from an external file
try:
    execfile(os.path.realpath("%s%s" % (os.path.splitext(__file__)[0],".conf")))
except Exception as e:
    print "Unable to load configuration file."
    sys.exit(-7)

#-----------------------------------------------------------------------
# End Settings
#-----------------------------------------------------------------------

#-----------------------------------------------------------------------
# Begin Code
#-----------------------------------------------------------------------

# Initialize our logging
logging.basicConfig(format="[%(asctime)s %(filename)s:%(lineno)d](%(levelno)d) %(message)s",filename=logFileName,level=logFileLevel)
logging.info("Starting run...")

# Validate our searchDirectory
searchDirectory = os.path.abspath(searchDirectory)
if not (os.access(searchDirectory, os.R_OK)):
    logging.error("Unable to read the searchDirectory '%s'" % (searchDirectory))
    sys.exit(-3)
logging.info("  searchDirectory: %s" % (searchDirectory))

# Validate our databaseFile
databaseFile = os.path.abspath(databaseFile)
if (os.path.exists(databaseFile)):
    if not (os.path.isfile(databaseFile)):
        logging.error("Unable to use invalid database file (exists as directory) '%s'" % (databaseFile))
        sys.exit(-2)
    if not (os.access(databaseFile, os.W_OK)):
        logging.error("Unable to write to database file '%s'" % (databaseFile))
        sys.exit(-4)
logging.info("  databaseFile: %s" % (databaseFile))
        
# Validate our fileExtensions
if (len(fileExtensions) < 1):
    logging.error("Unable to proceed with no file extensions defined.")
    sys.exit(-5)
logging.info("  fileExtensions: %s" % (fileExtensions))

# Initialize our database here
dbConn = None
try:
    dbConn = sqlite3.connect(databaseFile)
    dbConn.row_factory = sqlite3.Row
except Exception as e:
    logging.error("Unable to establish a connection with the database.")
    logging.debug("Extended data: %s" % (e))
    sys.exit(-6)
logging.info("Connected to our database...")
dbCursor = dbConn.cursor()

# Create tables if they do not already exist
try:
    logging.debug("Running database create on files if not present")
    dbCursor.execute("CREATE TABLE IF NOT EXISTS files (fileid text PRIMARY KEY, author text, title text, release_date text, path text, active int DEFAULT 0, createdrunid int, lastrunid int, published_locations text, filesize int, book text, chapter text, verse text)")
except Exception as e:
    logging.error("Unable to create table files.")
    logging.debug("Extended data: %s" % (e))

try:
    logging.debug("Running database create on downloads if not present")
    dbCursor.execute("CREATE TABLE IF NOT EXISTS downloads (fileid text PRIMARY KEY, count int, FOREIGN KEY(fileid) REFERENCES files(fileid))")
except Exception as e:
    logging.error("Unable to create table downloads.")
    logging.debug("Extended data: %s" % (e))
    
dbConn.commit()

# Generate a run ID
runID = int("%s%04d" % (time.strftime("%Y%m%d%H%M%S"),random.randint(0,9999)))
logging.debug("Generated runID '%d'." % (runID))

# Gather our files
for root, dirs, files in os.walk(searchDirectory):
    logging.debug("Exploring files in '%s'" % (root))
    for fileName in files:
        filePath = os.path.join(root,fileName)
        # Check to see if this file has extension we care about
        fileExtension = os.path.splitext(fileName)[1]
        if (fileExtension.lower() in fileExtensions):
            # We care about this file. Let's create an entry for it...
            logging.debug("We care about file '%s'" % (filePath))
            fileHash = None
            try:
                fileHash = hashlib.sha256(open(filePath, 'rb').read()).hexdigest()
            except Exception as e:
                logging.error("Unable to generate hash for file '%s'. It will be skipped." % (fileName))
                logging.debug("Extended data: %s" % (e))
                continue
            logging.debug("Generated file hash for '%s': '%s'" % (filePath, fileHash))
            fileExistsInDB = dbCursor.execute("SELECT COUNT(*) FROM files WHERE fileid=?",(fileHash,)).fetchone()[0]
            logging.debug("File exists in database? %d" % (fileExistsInDB))
            if not (fileExistsInDB):
                # Gather the data we need to insert a record
                fileTagLib = None
                try:
                    fileTagLib = taglib.File(filePath)
                    logging.debug("Gathered tag information from file: %s" % (fileTagLib.tags))
                except Exception as e:
                    logging.error("Unable to gather audio tag information from file '%s'. It will be skipped." % (filePath))
                    logging.debug("Extended data: %s" % (e))
                    continue
                
                # Get and check relevant tag information. Also, these are cast to strings because of Python 2.x; these are unicode values
                try:
                    fileArtist = str(fileTagLib.tags['ARTIST'][0])
                    fileTitle = str(fileTagLib.tags['TITLE'][0])
                except KeyError as e:
                    logging.error("Unable to gather artist/title information from file '%s'. It will be skipped." % (filePath))
                    logging.debug("Extended data: %s" % (e))
                    continue

                if ('RELEASE DATE' in fileTagLib.tags):
                    fileReleaseDate = str(fileTagLib.tags['RELEASE DATE'][0])
                else:
                    fileReleaseDate = "unknown"

		if ('BOOK' in fileTagLib.tags):
		    fileBook = str(fileTagLib.tags['BOOK'][0])
		else:
		    fileBook = "unknown"

                if ('CHAPTER' in fileTagLib.tags):
		    try:
                        fileChapter = str(fileTagLib.tags['CHAPTER'][0]).strip()
                    except ValueError as e:
                        logging.error("Unable to gather chapter information from file '%s'. The value could not be cast as an integer. It will be skipped." % (filePath))
                        fileChapter = -1

                if ('VERSES' in fileTagLib.tags):
                    fileVerse = str(fileTagLib.tags['VERSES'][0])
                else:
                    fileVerse = "unknown"
                
                if (len(fileArtist) < 1):
                    # No artist is not a valid selection.
                    logging.error("Unable to use file '%s' because the artist value is blank." % (filePath))
                    continue

		# Fix for "Speaker: " prefix for artist.
		if (fileArtist[0:9].lower() == "speaker: "):
		    tmpFileArtist = fileArtist[9:]
		    if (len(tmpFileArtist) > 0):
			logging.debug("Fixing 'Speaker' tag for file '%s'.")
		        fileArtist = tmpFileArtist
                    
                if (len(fileTitle) < 1):
                    # No title is not a valid selection.
                    logging.error("Unable to use file '%s' because the title value is blank." % (filePath))
                    continue
                    
                # Get the file size in bytes
                fileSize = os.path.getsize(filePath)
                
                try:
                    dbCursor.execute("INSERT INTO files(fileid,author,title,release_date,path,active,createdrunid,lastrunid,filesize,book,chapter,verse) VALUES (?,?,?,?,?,1,?,?,?,?,?,?)",(fileHash,fileArtist,fileTitle,fileReleaseDate,filePath,runID,runID,fileSize,fileBook,fileChapter,fileVerse))
                    dbConn.commit()
                except Exception as e:
                    logging.error("Unable to insert new file record for '%s'. It will be skipped." % (filePath))
                    logging.debug("Extended data: %s" % (e))
                    continue
                logging.info("Inserted new record for '%s' into database" % (filePath))
            else:
                try:
                    dbCursor.execute("UPDATE files SET lastrunid=? WHERE fileid=?",(runID,fileHash))
                    dbConn.commit()
                except Exception as e:
                    logging.error("Unable to refresh run status for file '%s'. It will be skipped (and marked inactive)." % (filePath))
                    logging.debug("Extended data: %s" % (e))
                    continue
                logging.debug("Refreshed run status for '%s'." % (filePath))
                
# Mark files as inactive if their last run ID doesn't match right now
try:
    dbCursor.execute("UPDATE files SET active=0 WHERE lastrunid <> ? AND active=1",(runID,))
    dbConn.commit()
    logging.info("Expired %d files from active status during this run" % (dbCursor.rowcount))
except Exception as e:
    logging.error("Unable to refresh active status for files. This will create integrity issues.")
    logging.debug("Extended data: %s" % (e))

# Create an email message for publishing
fileList = list()
try:
    dbCursor.execute("SELECT fileid,author,title,release_date FROM files WHERE createdrunid=?",(runID,))
    fileList = dbCursor.fetchmany(35)
except Exception as e:
    logging.error("Unable to retrieve updates from database for this run")
    logging.debug("Extended data: %s" % (e))

# We actually have some files to act upon
if (len(fileList) > 0):
    fileListText = "Release Date, Title, Pastor, File ID\n"
    for result in fileList:
        fileListText += "%s\n" % (", ".join([result["release_date"],result["title"],result["author"],result["fileid"]]))

    messageText = "The following audio files were successfully processed and published for listening on the web:\n\n"
    messageText += "--\n%s--\n\n" % (fileListText)
    if (len(fileList) > 35):
        messageText += "Additionally, more audio files were also published during this run but were omitted due to the size of this message. Please see the logs for more information.\n\n"
    messageText += "Thanks,\n%s\n" % (emailSender)

    # Try to connect to our email service:
    smtpReady = False
    try:
        smtpSession = smtplib.SMTP_SSL(smtpServer)
        smtpSession.login(smtpUsername,smtpPassword)
        smtpReady = True
    except smtplib.SMTPAuthenticationError as e:
        logging.error("Unable to connect to email service due to an authentication error.")
        logging.debug("Extended data: %s" % (e))
    except smtplib.SMTPException as e:
        logging.error("Unable to connect to email service due to an SMTP exception:")
        logging.error("Extended data: %s" % (e))
    except Exception as e:
        logging.error("Unable to connect to email service due to an unknown error:")
        logging.error("Extended data: %s" % (e))

    if (smtpReady):
        message = MIMEText(messageText)
        message['From'] = emailSender
        message['To'] = emailRecipient
        message['Subject'] = emailSubject % (runID)
        try:
            smtpSession.sendmail(emailSender,emailRecipient,message.as_string())
            logging.info("Sent email message about publishing...")
        except smtplib.SMTPException as e:
            logging.error("Unable to send email message due to an SMTP exception:")
            logging.error("Extended data: %s" % (e))
        except Exception as e:
            logging.error("Unable to send email message due to an unknown error:")
            logging.error("Extended data: %s" % (e))

else:
    logging.info("No email will be sent (no files added).")

dbConn.close()

logging.info("Ending run...")

#-----------------------------------------------------------------------
# End Code
#-----------------------------------------------------------------------

