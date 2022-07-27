from PyQt5.QtCore import QObject,pyqtSignal
import xmltodict
import os
import json
import time

killall = False
database = 'huntstats.db'

'''
def xmltodict(line):
    s = line.split('"')
    key = s[1]
    value = s[3]
    return { key : value }
'''

def diff(file1,file2):
    with open(file1,'r',encoding='utf-8') as f1:
        with open(file2,'r',encoding='utf-8') as f2:
            return f1.read() != f2.read()

def file_changed(filepath,last_change):
    return os.stat(filepath).st_mtime != last_change

def parse_value(value):
    if value.isnumeric():
        return int(value)
    elif value == 'true' or value == 'false':
        return 1 if value == 'true' else 0
    else:
        return value

class Logger(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(str)
    xml_path = ''
    json_out_dir = os.path.join(os.getcwd(),'json')
    if not os.path.exists(json_out_dir):
        os.makedirs(json_out_dir)

    def __init__(self):
        QObject.__init__(self)


    def set_path(self,huntpath):
        suffix = 'user/profiles/default/attributes.xml' 
        self.xml_path = os.path.join(huntpath,suffix)
        print(self.xml_path)
        if not os.path.exists(self.xml_path):
            self.print('attributes.xml not found.')
            print('attributes.xml not found.')
            return -1
        return 1

    def print(self,msg):
        print(msg)
        self.progress.emit(msg)


    def run(self):
        print(self.parent())
        global killall
        last_change = -1
        while True:
            if self.xml_path == '': continue

            if file_changed(self.xml_path,last_change):
                timestamp = int(os.stat(self.xml_path).st_mtime)

                json_outfile = os.path.join(self.json_out_dir,'attributes_'+str(timestamp)+'.json')
                json_outfile_wait = json_outfile + '.2'
                json_files = os.listdir(self.json_out_dir)

                sql_rows = self.build_json_from_xml()

                if len(os.listdir(self.json_out_dir)) == 0:
                    with open(json_outfile,'w',encoding='utf-8') as outfile:
                        json.dump(sql_rows,outfile,indent=True)
                else:
                    prev_json = os.path.join(self.json_out_dir,max(json_files,key=lambda x : os.stat(os.path.join(self.json_out_dir,x)).st_mtime))
                    with open(json_outfile_wait,'w',encoding='utf-8') as outfile:
                        json.dump(sql_rows,outfile,indent=True)
                    if not diff(prev_json,json_outfile_wait):
                        os.remove(json_outfile_wait)
                    else:
                        os.replace(json_outfile_wait,json_outfile)
                time.sleep(1)
                self.print(time.strftime('%m/%d %H:%M:%S\n') + ' waiting for changes....\n')

                last_change = os.stat(self.xml_path).st_mtime

            time.sleep(1)
            if killall:
                self.finished.emit()
                break

        
    def build_json_from_xml(self):
        self.print('building json object')
        sql_rows = {
                    'game' : {},
                    'hunter' : {},
                    'entry' : {},
                    'team' : {}
                }

        with open(self.xml_path,'r',encoding='utf-8') as xmlfile:
            points = 0
            for line in xmlfile:
                if 'MissionAccoladeEntry_' in line:
                    try:
                       linedict = xmltodict.parse(line)
                    except:
                        print(line)
                        continue
                    key = parse_value(linedict['Attr']['@name'])
                    value= parse_value(linedict['Attr']['@value'])
                    if value != '' and 'tooltip' not in key:
                        keysplit = key.split('_')
                        if 'MissionAccoladeEntry_' in key:
                            if "eventPoints" in key:
                                points += value
                                #sql_rows['game']['EventPoints'] = value
                if "MissionBag" in line:
                    try:
                        linedict = xmltodict.parse(line)
                    except:
                        print(line)
                        continue
                    key = parse_value(linedict['Attr']['@name'])
                    value = parse_value(linedict['Attr']['@value'])
                    if value != '' and 'tooltip' not in key:
                        keysplit = key.split('_')
                        if 'MissionBagPlayer_' in key:
                            team_num = int(keysplit[1])
                            hunter_num = int(keysplit[2])
                            if team_num not in sql_rows['hunter'].keys():
                                sql_rows['hunter'][team_num] = {}
                            if hunter_num not in sql_rows['hunter'][team_num].keys():
                                sql_rows['hunter'][team_num][hunter_num] = {'team_num':team_num,'hunter_num':hunter_num}
                            category = '_'.join(keysplit[3:])
                            sql_rows['hunter'][team_num][hunter_num][category] = value
                        elif 'MissionBagTeam_' in key:
                            team_num = int(keysplit[1])
                            if team_num not in sql_rows['team'].keys():
                                sql_rows['team'][team_num] = {'team_num':team_num}
                            if len(keysplit) > 2:
                                category = '_'.join(keysplit[2:])
                                sql_rows['team'][team_num][category] = value
                        elif 'MissionBagEntry_' in key:
                            entry_num = int(keysplit[1])
                            if entry_num not in sql_rows['entry'].keys():
                                sql_rows['entry'][entry_num] = {'entry_num':entry_num}
                            if len(keysplit) > 2:
                                category = '_'.join(keysplit[2:])
                                sql_rows['entry'][entry_num][category] = value
                        elif 'Entry_' not in key:
                            sql_rows['game'][key] = value
            print('points',points)
            sql_rows['game']['EventPoints'] = points
        return self.clean_json(sql_rows)

    def clean_json(self,sql_rows):
        num_teams = sql_rows['game']['MissionBagNumTeams']
        teams = sql_rows['team']
        hunters = sql_rows['hunter']
        teams_to_remove = []
        for teamnum in teams:
            if int(teamnum) > num_teams:
                teams_to_remove.append(teamnum)
        for teamnum in teams_to_remove:
            sql_rows['team'].pop(teamnum)
            sql_rows['hunter'].pop(teamnum)
        
        hunters_per_team = { teams[n]['team_num'] : teams[n]['numplayers'] for n in teams} 

        for teamnum in hunters:
            numhunters = hunters_per_team[int(teamnum)]
            hunters_to_remove = []
            team = hunters[teamnum]
            for hunternum in team:
                hunter = team[hunternum]
                if hunter['hunter_num'] > numhunters:
                    hunters_to_remove.append(hunternum)
            for hunternum in hunters_to_remove:
                hunters[teamnum].pop(hunternum)
        return sql_rows