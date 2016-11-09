# -*- coding: utf-8 -*-
import codecs
import datetime
import logging
import re

from google.appengine.api import memcache, users

from google.appengine.ext import ndb


class Semester(ndb.Model):
	year = ndb.IntegerProperty(required=True)
	ht = ndb.BooleanProperty(required=True)

	@staticmethod
	def getid(year, ht):
		return str(year) + ("ht" if ht else "vt")

	@staticmethod
	def create(year, ht):
		if year < 2016:
			raise ValueError("Invalid year %d" % year)
		return Semester(id=Semester.getid(year, ht), year=year, ht=ht)
		
	@staticmethod
	def getOrCreateCurrent():
		thisdate = datetime.datetime.now()
		ht = True if thisdate.month>6 else False
		semester = Semester.get_by_id(Semester.getid(thisdate.year + 1, ht))
		if semester == None:
			semester = Semester.create(thisdate.year + 1, ht)
			semester.put()
		return semester

	def getyear(self):
		return self.year

	def getname(self):
		return "%04d-%s" % (self.getyear(), "ht" if self.ht else "vt")

# kår
class ScoutGroup(ndb.Model):
	name = ndb.StringProperty(required=True)
	activeSemester = ndb.KeyProperty(kind=Semester)
	organisationsnummer = ndb.StringProperty()
	foreningsID = ndb.StringProperty()
	kommunID = ndb.StringProperty(default="1480")

	@staticmethod
	def getid(name):
		return name.lower().replace(' ', '')

	@staticmethod
	def create(name):
		if len(name) < 2:
			raise ValueError("Invalid name %s" % (name))
		return ScoutGroup(id=ScoutGroup.getid(name), name=name)
	
	@staticmethod
	def getgroupsforuser(user):
		if user.groupaccess != None:
			return [user.groupaccess.get()]
		else:
			return ScoutGroup.query().fetch(100)

	def getname(self):
		return self.name

# avdelning
class Troop(ndb.Model):
	name = ndb.StringProperty()
	scoutgroup = ndb.KeyProperty(kind=ScoutGroup)
	defaultstarttime = ndb.StringProperty(default="18:30")
	rapportID = ndb.IntegerProperty()

	@staticmethod
	def getid(name, scoutgroup_key):
		return name.lower().replace(' ', '')+scoutgroup_key.id()

	@staticmethod
	def create(name, scoutgroup_key):
		return Troop(id=Troop.getid(name, scoutgroup_key), name=name, scoutgroup=scoutgroup_key)

	def getname(self):
		return self.name

class Person(ndb.Model):
	firstname = ndb.StringProperty(required=True)
	lastname = ndb.StringProperty(required=True)
	birthdate = ndb.DateProperty(required=True) # could be a computed property from personnr
	personnr = ndb.StringProperty()
	female = ndb.BooleanProperty(required=True)
	troop = ndb.KeyProperty(kind=Troop) # assigned default troop in scoutnet, can be member of multiple troops 
	patrool = ndb.StringProperty()
	scoutgroup = ndb.KeyProperty(kind=ScoutGroup)
	notInScoutnet = ndb.BooleanProperty()
	removed = ndb.BooleanProperty()
	email = ndb.StringProperty()
	phone = ndb.StringProperty()
	mobile = ndb.StringProperty()
	_dirty = False

	def __init__(self, *args, **kw):
		self._dirty = False
		super(Person, self).__init__(*args, **kw)

	def __setattr__(self, key, value):
		if key[:1] != '_': # avoid all system properties and "_dirty"
			if self.__getattribute__(key) != value:
				self._make_dirty()
		super(Person, self).__setattr__(key, value)

	def _make_dirty(self):
		self._dirty = True

	def _not_dirty(self):
		self._dirty = False

	@staticmethod
	def create(id, firstname, lastname, personnr, female):
		return Person(id=id,
			firstname=firstname,
			lastname=lastname,
			birthdate=Person.persnumbertodate(personnr),
			female=female,
			personnr=personnr)

	@staticmethod
	def createlocal(firstname, lastname, personnr, female):
		return Person(
			firstname=firstname,
			lastname=lastname,
			birthdate=Person.persnumbertodate(personnr),
			female=female,
			personnr=personnr,
			notInScoutnet=True)

	@staticmethod
	def persnumbertodate(pnr):
		return datetime.datetime.strptime(pnr[:8], "%Y%m%d").date()
	
	def setpersonnr(self, pnr):
		self.personnr = pnr.replace('-', '')
		self.birthdate = Person.persnumbertodate(pnr)
	
	def getpersonnr(self):
		return self.personnr.replace('-', '')
		
	def getbirthdatestring(self):
		return self.birthdate.strftime("%Y-%m-%d")
	def getpersnumberstr(self):
		return self.birthdate.strftime("%Y%m%d0000")

	def getname(self):
		pattern = re.compile("\( -")
		fn = self.firstname #pattern.split(self.firstname)[0][:10]
		ln = pattern.split(self.lastname)[0][:12]
		return fn + " " + ln
	
	def getyearsoldthisyear(self, year):
		return year - self.birthdate.year

class Meeting(ndb.Model):
	datetime = ndb.DateTimeProperty(auto_now_add=True, required=True)
	name = ndb.StringProperty(required=True)
	troop = ndb.KeyProperty(kind=Troop, required=True)
	duration = ndb.IntegerProperty(default=90, required=True) #minutes
	semester = ndb.KeyProperty(kind=Semester, required=True)
	attendingPersons = ndb.KeyProperty(kind=Person, repeated=True) # list of attending persons' keys

	@staticmethod
	def create(troop_key, name, datetime, duration, semester_key):
		return Meeting(id=datetime.strftime("%Y%m%d%H%M")+str(troop_key.id())+str(semester_key.id()),
			datetime=datetime,
			name=name,
			troop=troop_key,
			duration=duration,
			semester=semester_key
			)

	@staticmethod
	def gettroopmeetings(troop_key, semester_key): # TODO: memcache here!
		return Meeting.query(Meeting.troop==troop_key, Meeting.semester==semester_key).order(-Meeting.datetime)

	def commit(self):
		self.put()

	def getdate(self):
		return self.datetime.strftime("%Y-%m-%d")
	def gettime(self):
		return self.datetime.strftime("%H:%M")
	def getname(self):
		return self.name

class TroopPerson(ndb.Model):
	troop = ndb.KeyProperty(kind=Troop, required=True)
	person = ndb.KeyProperty(kind=Person, required=True)
	leader = ndb.BooleanProperty(default=False)
	sortname = ndb.ComputedProperty(lambda self: self.person.get().getname().lower())

	@staticmethod
	def getid(troop_key, person_key):
		return str(troop_key.id())+str(person_key.id())

	@staticmethod
	def __getMemcacheKeyString(troop_key):
		return 'tps:' + str(troop_key)
	
	def delete(self):
		self.key.delete()
		troopperson_keys = memcache.get(TroopPerson.__getMemcacheKeyString(self.troop))
		if troopperson_keys is not None:
			troopperson_keys.remove(self.key)
			memcache.replace(TroopPerson.__getMemcacheKeyString(self.troop), troopperson_keys)

	@staticmethod
	def create(troop_key, person_key, isLeader):
		tp = TroopPerson(id=TroopPerson.getid(troop_key, person_key),
			troop=troop_key,
			person=person_key,
			leader=isLeader)
		troopperson_keys = memcache.get(TroopPerson.__getMemcacheKeyString(troop_key))
		if troopperson_keys is not None and tp.key not in troopperson_keys:
			troopperson_keys.append(tp.key)
			memcache.replace(TroopPerson.__getMemcacheKeyString(troop_key), troopperson_keys)
		return tp

	def put(self):
		super(TroopPerson, self).put()
	
	@staticmethod
	def getTroopPersonsForTroop(troop_key):
		trooppersons = []
		troopperson_keys = memcache.get(TroopPerson.__getMemcacheKeyString(troop_key))
		if troopperson_keys is None:
			troopperson_keys = TroopPerson.query(TroopPerson.troop==troop_key).fetch(keys_only=True)
			memcache.add(TroopPerson.__getMemcacheKeyString(troop_key), troopperson_keys)
		for tp_key in troopperson_keys:
			tp = tp_key.get()
			if tp != None:
				trooppersons.append(tp)
		trooppersons.sort(key=lambda x: (-x.leader, x.sortname))
		return trooppersons

	def commit(self):
		self.put()

	def getname(self):
		return self.person.get().getname()

	def gettroopname(self):
		return self.troop.get().getname()

class UserPrefs(ndb.Model):
	userid = ndb.StringProperty(required=True)
	hasaccess = ndb.BooleanProperty(required=True)
	canimport = ndb.BooleanProperty(required=False)
	hasadminaccess = ndb.BooleanProperty(default=False, required=True)
	name = ndb.StringProperty(required=True)
	activeSemester = ndb.KeyProperty(kind=Semester)
	groupaccess = ndb.KeyProperty(kind=ScoutGroup, required=False, default=None)
	groupadmin = ndb.BooleanProperty(required=False, default=False)

	def hasAccess(self):
		return self.hasaccess

	def isAdmin(self):
		return self.hasaccess and self.hasadminaccess

	def canImport(self):
		return self.hasaccess and self.canimport

	def getname(self):
		return self.name

	@staticmethod
	def current():
		cu = users.get_current_user()
		return UserPrefs.getorcreate(cu)

	def updateMemcache(self):
		if not memcache.add(self.userid, self):
			memcache.replace(self.userid, self)

	def put(self):
		super(UserPrefs, self).put()
		self.updateMemcache()

	@staticmethod
	def getorcreate(user):
		userprefs = memcache.get(user.user_id())
		if userprefs is not None:
			return userprefs
		else:
			usersresult = UserPrefs.query(UserPrefs.userid == user.user_id()).fetch()
			if len(usersresult) == 0:
				userprefs = UserPrefs.create(user, users.is_current_user_admin(), users.is_current_user_admin())
				userprefs.put()
			else:
				userprefs = usersresult[0]
				userprefs.updateMemcache()
			return userprefs

	@staticmethod
	def create(user, access=False, hasadminaccess=False):
		return UserPrefs(userid=user.user_id(), name=user.nickname(), hasaccess=access, hasadminaccess=hasadminaccess)
