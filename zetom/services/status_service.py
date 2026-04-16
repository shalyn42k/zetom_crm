from permissions import ROLE_PERMISSIONS
from .models import RequestMain, Oferta, zlecenie, wniosek
from statuses import Status, ArchiveState

new_request = form.save()
def handle_child_change(new_request):
    change_status(new_request)
    update_parent_status(new_request)
    archive_if_done(new_request)
    unarchive(new_request)
    
# изменение, создание , удаление ребёнка
# после update_parent_status выполняется archive_if_done
# после archive_if_done выполняется unarchive
def change_status(models.Model):# в скобках пишем название функции/класса откуда будем брать статусы   
    Transition = {
        "new": ["in_proger"],
        "in_progress": ["waiting"],
        "waiting": ["done"],
        "done": ["in_progress", "waiting"]
    }






# тут пишем проверку перехода статусов. например с new в in progews
# что он может
# если все ок, мы меняем статусы 
# если не ок, то мы не даем доступ

def update_parent_status():# пишем название функции RequestMain


# анализ статусов детей 
# после чего оно выберае высокий статус и даем его родителю
#пример :
 # если есть in_progress → in_progress
 # иначе если есть waiting → waiting
  # иначе если есть new → new
  # иначе → done
# то статус обновляется по сравнению статуса ребенка 

# если удаляется дубль ребенок то тригер archive_if_done 
# если любой ребенок получает статус done - тригер archive if done 
def archive_if_done():# пишем название функции RequestMain


# 
# проверка если ли дети
# проверка на статус родителя 
#
# считает сколько детей у текущего родитиля
# стравнивает done количеству детей 
# если количество детей больше нуля и все done то родитель archive 
# if количество детей не равно done, то цикл остается прежним 


# если нет детей то ничего не детаем 

def unarchive():

    # если родитель archive и появился ребенок не done, то родитель active

