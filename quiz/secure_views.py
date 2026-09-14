import random
import re

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, Http404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group

from auth_system.models import MyUser
from judge.models import ClassName, KnowledgePoint1, KnowledgePoint2, ChoiceProblem, DuchengProblem
from work.models import BanJi
from .models import AnswerRecord


def _student_banjis(user):
    return BanJi.objects.filter(students=user).select_related('teacher', 'courser')


def _student_courses(user):
    course_ids = _student_banjis(user).values_list('courser_id', flat=True).distinct()
    return ClassName.objects.filter(id__in=course_ids).prefetch_related('knowledgepoint1_set__knowledgepoint2_set')


ROUND_SIZE = 10


def _kp2_total_questions(kp2):
    return ChoiceProblem.objects.filter(knowledgePoint2=kp2).count() + DuchengProblem.objects.filter(knowledgePoint2=kp2).count()


def _kp2_round_size(kp2):
    """每轮固定 10 题；题库不足时保留旧数据的可用题量。"""
    return min(ROUND_SIZE, _kp2_total_questions(kp2))


def _record_question_key(record):
    question_id = record.choice_question_id if record.question_type == AnswerRecord.CHOICE else record.ducheng_question_id
    return '%s:%s' % (record.question_type, question_id)


def _kp2_completed_rounds(user, kp2):
    round_size = _kp2_round_size(kp2)
    if round_size <= 0:
        return 0
    q_per_round = {}
    for record in AnswerRecord.objects.filter(user=user, kp2=kp2):
        q_per_round.setdefault(record.round_num, set()).add(_record_question_key(record))
    return sum(1 for qs in q_per_round.values() if len(qs) >= round_size)


def _kp2_highest_correct(user, kp2_id):
    per_round = {}
    for record in AnswerRecord.objects.filter(user=user, kp2_id=kp2_id):
        per_round.setdefault(record.round_num, 0)
        if record.is_correct:
            per_round[record.round_num] += 1
    return max(per_round.values()) if per_round else 0


def _score_bars(highest_correct, round_size):
    if round_size <= 0 or highest_correct <= 0:
        return 0, '#e0e0e0'
    pct = highest_correct * 100.0 / round_size
    if pct > 80:
        return 3, '#5cb85c'
    if pct >= 60:
        return 2, '#f0ad4e'
    return 1, '#d9534f'


def _course_accessible(user, course):
    return _student_banjis(user).filter(courser=course).exists()


def _kp2_accessible(user, kp2):
    if not kp2.upperPoint:
        return False
    if not _course_accessible(user, kp2.upperPoint.classname):
        return False
    prev_complete = True
    for item in kp2.upperPoint.knowledgepoint2_set.all().order_by('id'):
        total = _kp2_total_questions(item)
        if item.pk == kp2.pk:
            return total <= 0 or prev_complete
        if total > 0:
            prev_complete = prev_complete and (_kp2_completed_rounds(user, item) >= 1)
    return False


def _first_banji_for_course(user, course):
    return _student_banjis(user).filter(courser=course).first()


def _student_group():
    return Group.objects.filter(name='学生').first()


def _ensure_student_group(user):
    group, _ = Group.objects.get_or_create(name='学生')
    if not user.groups.filter(pk=group.pk).exists():
        user.groups.add(group)


@login_required
def kp_tree(request):
    if request.user.is_content_admin:
        return redirect('list_coursers')
    if request.user.isTeacher():
        return redirect('banji_list')

    if not _student_banjis(request.user).exists():
        return render(request, 'quiz/join_banji.html', {
            'title': '加入班级',
            'position': 'quiz_join_banji',
            'banjis': [],
            'message': '',
            'error': '',
        })

    course_data = []
    for course in _student_courses(request.user):
        kp1_list = []
        course_prev_complete = True
        for idx, kp1 in enumerate(course.knowledgepoint1_set.all()):
            kp2_list = []
            kp1_correct = 0
            kp1_answered = 0
            kp1_total = 0
            prev_complete = course_prev_complete
            for kp2 in kp1.knowledgepoint2_set.all():
                total = _kp2_total_questions(kp2)
                all_recs = AnswerRecord.objects.filter(user=request.user, kp2=kp2)
                round_size = _kp2_round_size(kp2)
                highest_correct = _kp2_highest_correct(request.user, kp2.id)
                completed_rounds = _kp2_completed_rounds(request.user, kp2)
                bar_count, bar_color = _score_bars(highest_correct, round_size)
                kp1_correct += highest_correct
                kp1_answered += all_recs.count()
                kp1_total += total
                kp2_list.append({
                    'id': kp2.id,
                    'name': kp2.name,
                    'total': total,
                    'answered': all_recs.count(),
                    'highest_correct': highest_correct,
                    'round_size': round_size,
                    'bar_count': bar_count,
                    'bar_color': bar_color,
                    'complete': completed_rounds >= 1,
                    'locked': not prev_complete and total > 0,
                })
                if total > 0:
                    prev_complete = prev_complete and (completed_rounds >= 1)
            course_prev_complete = prev_complete
            if kp2_list:
                kp1_list.append({
                    'id': kp1.id, 'name': kp1.name, 'kp2s': kp2_list,
                    'index': idx + 1,
                    'total_correct': kp1_correct,
                    'total_answered': kp1_answered,
                    'total_qs': kp1_total,
                    'show_ellipsis': False,
                })
        if len(kp1_list) > 3:
            for i, kp1_item in enumerate(kp1_list):
                kp1_item['hidden'] = (i >= 3)
            kp1_list[2]['show_ellipsis'] = True
            kp1_list[2]['remaining'] = len(kp1_list) - 3
        if kp1_list:
            course_data.append({'id': course.id, 'name': course.name, 'kp1s': kp1_list})

    return render(request, 'quiz/kp_tree.html', {
        'title': '自主练习',
        'position': 'quiz_kp_tree',
        'course_data': course_data,
        'need_join_class': False,
        'total_points': AnswerRecord.objects.filter(user=request.user, is_correct=True).count(),
    })


@login_required
def join_banji(request):
    if request.user.isTeacher() or request.user.is_content_admin:
        raise Http404()

    _ensure_student_group(request.user)

    message = ''
    error = ''
    if request.method == 'POST':
        code = request.POST.get('banji_code', '').strip()
        if not (code.isdigit() and len(code) == 6):
            error = '班级码必须是 6 位数字'
        else:
            banji = BanJi.objects.filter(join_code=code).select_related('teacher', 'courser').first()
            if not banji:
                error = '未找到该班级'
            elif banji.students.filter(pk=request.user.pk).exists():
                message = '你已经加入该班级'
            else:
                banji.students.add(request.user)
                message = '加入班级成功'

    return render(request, 'quiz/join_banji.html', {
            'title': '加入班级',
        'position': 'quiz_join_banji',
        'banjis': _student_banjis(request.user),
        'message': message,
        'error': error,
    })


@login_required
def answer_question(request, kp2_id):
    if request.user.isTeacher() or request.user.is_content_admin:
        raise Http404()
    kp2 = get_object_or_404(KnowledgePoint2, pk=kp2_id)
    if not _kp2_accessible(request.user, kp2):
        raise Http404()

    all_records = AnswerRecord.objects.filter(user=request.user, kp2=kp2)
    round_size = _kp2_round_size(kp2)
    if round_size == 0:
        return render(request, 'quiz/kp2_complete.html', {
            'title': '自主练习',
            'kp2': kp2,
            'correct': 0, 'total': 0, 'round': 0, 'max_rounds': 3,
            'next_url': None,
        })

    q_per_round = {}
    for r in all_records:
        q_per_round.setdefault(r.round_num, set()).add(_record_question_key(r))

    show_done = request.GET.get('done')
    if show_done:
        try:
            round_num = int(show_done)
        except ValueError:
            round_num = 0
        round_score = AnswerRecord.objects.filter(
            user=request.user, kp2=kp2, round_num=round_num, is_correct=True
        ).count()
        highest_correct = _kp2_highest_correct(request.user, kp2.id)
        return render(request, 'quiz/kp2_round_done.html', {
            'title': '自主练习',
            'kp2': kp2,
            'round': round_num,
            'round_score': round_score,
            'round_size': round_size,
            'highest_correct': highest_correct,
        })

    work_round = max(q_per_round.keys()) if q_per_round else 1
    if len(q_per_round.get(work_round, set())) >= round_size:
        work_round += 1

    cur_answered = len(q_per_round.get(work_round, set()))
    cur_correct = q_per_round.get(work_round, set())
    choice_available = [q for q in ChoiceProblem.objects.filter(knowledgePoint2__id=kp2_id) if 'choice:%s' % q.id not in cur_correct]
    ducheng_available = [q for q in DuchengProblem.objects.filter(knowledgePoint2__id=kp2_id) if 'ducheng:%s' % q.ducheng_id not in cur_correct]
    merged = []
    for qt, pl in (('choice', choice_available), ('ducheng', ducheng_available)):
        for q in pl:
            merged.append((qt, q))
    if not merged:
        return render(request, 'quiz/kp2_round_done.html', {
            'title': '自主练习',
            'kp2': kp2,
            'round': work_round,
            'round_score': 0,
            'round_size': round_size,
            'highest_correct': _kp2_highest_correct(request.user, kp2.id),
        })
    random.shuffle(merged)
    qtype, question = merged[0]

    context = {
        'title': kp2.name,
        'position': 'quiz_kp_tree',
        'kp2': kp2,
        'question': question,
        'progress': {'round': work_round, 'cur_answered': cur_answered, 'total': round_size},
    }
    if qtype == 'ducheng':
        return render(request, 'quiz/answer_ducheng.html', context)
    return render(request, 'quiz/answer.html', context)


@login_required
def submit_answer(request, kp2_id):
    if request.user.isTeacher() or request.user.is_content_admin:
        raise Http404()
    kp2 = get_object_or_404(KnowledgePoint2, pk=kp2_id)
    if not _kp2_accessible(request.user, kp2):
        raise Http404()

    qtype = request.POST.get('question_type', 'choice')
    if qtype == 'choice':
        question_id = request.POST.get('question_id')
        selected = request.POST.get('selected', '').strip().lower()
        if not question_id or selected not in ('a', 'b', 'c', 'd'):
            return JsonResponse({'error': 'Invalid parameters'}, status=400)
        question = get_object_or_404(ChoiceProblem, pk=question_id)
        if not question.knowledgePoint2.filter(pk=kp2_id).exists():
            return JsonResponse({'error': 'Question does not belong to this knowledge point'}, status=400)
        is_correct = (selected == question.right_answer)
        round_size = _kp2_round_size(kp2)
        all_records = AnswerRecord.objects.filter(user=request.user, kp2=kp2)
        q_per_round = {}
        for r in all_records:
            q_per_round.setdefault(r.round_num, set()).add(_record_question_key(r))
        work_round = max(q_per_round.keys()) if q_per_round else 1
        if len(q_per_round.get(work_round, set())) >= round_size:
            work_round += 1
        points = 1 if is_correct else 0
        banji = _first_banji_for_course(request.user, kp2.upperPoint.classname)
        AnswerRecord.objects.create(
            user=request.user, question_type='choice', choice_question=question, kp2=kp2, banji=banji,
            is_correct=is_correct, points=points, round_num=work_round, student_answer=selected,
        )
        cnt_choice = AnswerRecord.objects.filter(user=request.user, kp2=kp2, round_num=work_round, question_type='choice').values('choice_question_id').distinct().count()
        cnt_ducheng = AnswerRecord.objects.filter(user=request.user, kp2=kp2, round_num=work_round, question_type='ducheng').values('ducheng_question_id').distinct().count()
        done_rnd = work_round if (cnt_choice + cnt_ducheng) >= round_size else None
        return JsonResponse({
            'correct': is_correct,
            'qtype': 'choice',
            'right_answer': question.right_answer,
            'selected': selected,
            'explanation': question.explanation or '',
            'done': done_rnd,
        })

    question_id = request.POST.get('question_id')
    student_answer = request.POST.get('selected', '').strip()
    if not question_id or not student_answer:
        return JsonResponse({'error': 'Answer required'}, status=400)
    question = get_object_or_404(DuchengProblem, pk=question_id)
    if not question.knowledgePoint2.filter(pk=kp2_id).exists():
        return JsonResponse({'error': 'Question does not belong to this knowledge point'}, status=400)
    correct_answers = [a.strip() for a in question.answer.split('|||') if a.strip()]
    is_correct = student_answer in correct_answers
    round_size = _kp2_round_size(kp2)
    all_records = AnswerRecord.objects.filter(user=request.user, kp2=kp2)
    q_per_round = {}
    for r in all_records:
        q_per_round.setdefault(r.round_num, set()).add(_record_question_key(r))
    work_round = max(q_per_round.keys()) if q_per_round else 1
    if len(q_per_round.get(work_round, set())) >= round_size:
        work_round += 1
    points = 1 if is_correct else 0
    banji = _first_banji_for_course(request.user, kp2.upperPoint.classname)
    AnswerRecord.objects.create(
        user=request.user, question_type='ducheng', ducheng_question=question, kp2=kp2, banji=banji,
        is_correct=is_correct, points=points, round_num=work_round, student_answer=student_answer,
    )
    cnt_choice = AnswerRecord.objects.filter(user=request.user, kp2=kp2, round_num=work_round, question_type='choice').values('choice_question_id').distinct().count()
    cnt_ducheng = AnswerRecord.objects.filter(user=request.user, kp2=kp2, round_num=work_round, question_type='ducheng').values('ducheng_question_id').distinct().count()
    done_rnd = work_round if (cnt_choice + cnt_ducheng) >= round_size else None
    return JsonResponse({
        'correct': is_correct,
        'qtype': 'ducheng',
        'right_answer': question.answer,
        'selected': student_answer,
        'explanation': question.explanation or '',
        'done': done_rnd,
    })


@login_required
def my_points(request):
    if request.user.isTeacher() or request.user.is_content_admin:
        raise Http404()
    all_my = AnswerRecord.objects.filter(user=request.user)
    total_correct = all_my.filter(is_correct=True).count()
    total_answered = all_my.count()
    accuracy = round(total_correct * 100 / total_answered, 1) if total_answered > 0 else 0
    kp2_data = []
    total_points = 0
    all_kp2s = KnowledgePoint2.objects.filter(answerrecord__user=request.user).distinct()
    for kp2 in all_kp2s:
        highest = _kp2_highest_correct(request.user, kp2.id)
        round_size = _kp2_round_size(kp2)
        total_points += highest
        kp2_data.append({'name': kp2.name, 'kp1_name': kp2.upperPoint.name if kp2.upperPoint else '', 'correct': highest, 'total': round_size})
    return render(request, 'quiz/my_points.html', {'title': '我的积分', 'position': 'quiz_points', 'total_points': total_points, 'total_answered': total_answered, 'total_correct': total_correct, 'accuracy': accuracy, 'kp2_data': kp2_data})


@login_required
def leaderboard(request):
    if request.user.isTeacher() or request.user.is_content_admin:
        raise Http404()
    my_banjis = _student_banjis(request.user)
    banji_rankings = []
    student_group = _student_group()
    for banji in my_banjis:
        students = banji.students.filter(groups=student_group) if student_group else banji.students.all()
        rankings = []
        for stu in students:
            total = 0
            # AnswerRecord 默认按 created_time 排序；若直接 distinct()，SQLite
            # 会把排序字段一并纳入 DISTINCT，导致同一知识点被重复统计。
            # 清除默认排序后再按知识点主键去重，确保每个知识点只计一次。
            kp2_ids = (AnswerRecord.objects.filter(user=stu)
                       .order_by()
                       .values_list('kp2_id', flat=True)
                       .distinct())
            for kp2_id in kp2_ids:
                total += _kp2_highest_correct(stu, kp2_id)
            rankings.append({'user__username': stu.username, 'user__id_num': stu.id_num, 'user_id': stu.id, 'points': total})
        rankings.sort(key=lambda r: r['points'], reverse=True)
        my_rank = None
        my_points_val = None
        for idx, row in enumerate(rankings):
            row['rank'] = idx + 1
            if row['user_id'] == request.user.id:
                my_rank = idx + 1
                my_points_val = row['points']
        banji_rankings.append({'banji_name': banji.name, 'rankings': rankings[:50], 'my_rank': my_rank, 'my_points': my_points_val, 'total_students': len(rankings)})
    return render(request, 'quiz/leaderboard.html', {'title': '积分排行榜', 'position': 'quiz_leaderboard', 'banji_rankings': banji_rankings})


@login_required
def teacher_class_progress(request, banji_id):
    """查看某个班级的自主练习情况：顶部班级概况，下方学生答题进度，可展开学生答题记录"""
    if request.user.is_content_admin or not request.user.isTeacher():
        raise Http404()

    banji = get_object_or_404(BanJi, pk=banji_id)
    # 确保只有该班的教师能查看
    if banji.teacher != request.user and not request.user.is_superuser:
        raise Http404()

    student_group = Group.objects.get(name='学生')
    students = banji.students.filter(groups=student_group)

    # 班级概况统计（页面顶部展示）
    student_ids = students.values_list('id', flat=True)
    total_answered = AnswerRecord.objects.filter(banji=banji, user__in=student_ids).count()
    total_correct = AnswerRecord.objects.filter(banji=banji, user__in=student_ids, is_correct=True).count()
    active_count = AnswerRecord.objects.filter(banji=banji, user__in=student_ids).values('user').distinct().count()
    class_stats = {
        'name': banji.name,
        'code': banji.join_code or banji.id,
        'student_count': students.count(),
        'active_count': active_count,
        'total_answered': total_answered,
        'total_correct': total_correct,
        'correct_rate': round(total_correct * 100 / total_answered, 1) if total_answered > 0 else 0,
    }

    # 学生自主练习情况（答题进度那一栏）
    student_data = []
    for stu in students:
        c = AnswerRecord.objects.filter(user=stu, banji=banji, is_correct=True).count()
        a = AnswerRecord.objects.filter(user=stu, banji=banji).count()
        student_data.append({
            'id': stu.id,
            'username': stu.username,
            'id_num': stu.id_num,
            'total_correct': c,
            'total_answered': a,
        })

    # 按积分降序排
    student_data.sort(key=lambda x: x['total_correct'], reverse=True)

    context = {
        'title': '%s - 自主练习情况' % banji.name,
        'position': 'banji_manage',
        'banji': banji,
        'class_stats': class_stats,
        'student_data': student_data,
    }

    # 若指定了学生，加载其答题记录并内嵌到本页下方
    student_id = request.GET.get('student')
    if student_id:
        stu = students.filter(pk=student_id).first()
        if stu is not None:
            records = AnswerRecord.objects.filter(
                user=stu, banji=banji
            ).select_related('choice_question', 'ducheng_question', 'kp2', 'kp2__upperPoint').order_by('-created_time')[:200]
            wrong_records = AnswerRecord.objects.filter(
                user=stu, banji=banji, is_correct=False
            ).select_related('choice_question', 'ducheng_question', 'kp2', 'kp2__upperPoint').order_by('-created_time')[:200]

            # 按知识点汇总
            kp2_summary = []
            kp2_ids = AnswerRecord.objects.filter(user=stu, banji=banji).values_list('kp2', flat=True).distinct()
            base_qs = AnswerRecord.objects.filter(user=stu, banji=banji)
            for kp2_id in kp2_ids:
                kp2 = KnowledgePoint2.objects.get(pk=kp2_id)
                correct = base_qs.filter(kp2=kp2, is_correct=True).count()
                total = base_qs.filter(kp2=kp2).count()
                kp2_summary.append({
                    'name': kp2.name,
                    'kp1_name': kp2.upperPoint.name if kp2.upperPoint else '',
                    'correct': correct,
                    'total': total,
                })

            tc = base_qs.filter(is_correct=True).count()
            tn = base_qs.count()

            context.update({
                'selected_stu': stu,
                'records': records,
                'wrong_records': wrong_records,
                'kp2_summary': kp2_summary,
                'total_correct': tc,
                'total_count': tn,
                'total_wrong': tn - tc,
            })

    return render(request, 'quiz/teacher_class_progress.html', context)


@login_required
def teacher_class_code_update(request, banji_id):
    """在班级自主练习情况页内联修改班级码"""
    if request.user.is_content_admin or not request.user.isTeacher():
        raise Http404()
    banji = get_object_or_404(BanJi, pk=banji_id)
    if banji.teacher != request.user and not request.user.is_superuser:
        raise Http404()
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': '请求方式错误'})

    new_code = request.POST.get('join_code', '').strip()
    if not new_code:
        return JsonResponse({'success': False, 'error': '班级码不能为空'})
    if not re.fullmatch(r'\d{6}', new_code):
        return JsonResponse({'success': False, 'error': '班级码必须是 6 位数字'})
    if BanJi.objects.filter(join_code=new_code).exclude(pk=banji.id).exists():
        return JsonResponse({'success': False, 'error': '班级码已存在，请换一个'})

    banji.join_code = new_code
    banji.save()
    return JsonResponse({'success': True, 'code': new_code})


@login_required
def teacher_kp_manage(request):
    if request.user.is_content_admin or not request.user.isTeacher():
        raise Http404()
    kp2s = KnowledgePoint2.objects.all().select_related('upperPoint__classname')
    kp2_data = []
    for kp2 in kp2s:
        total = ChoiceProblem.objects.filter(knowledgePoint2=kp2).count()
        kp2_data.append({'id': kp2.id, 'name': kp2.name, 'kp1_name': kp2.upperPoint.name if kp2.upperPoint else '', 'course_name': kp2.upperPoint.classname.name if kp2.upperPoint else '', 'total': total})
    return render(request, 'quiz/teacher_kp_manage.html', {'title': '知识点管理', 'position': 'quiz_teacher_kp_manage', 'kp2_data': kp2_data})


@login_required
def teacher_kp_questions(request, kp2_id):
    if request.user.is_content_admin or not request.user.isTeacher():
        raise Http404()
    kp2 = get_object_or_404(KnowledgePoint2, pk=kp2_id)
    choice_qs = ChoiceProblem.objects.filter(knowledgePoint2=kp2).order_by('-id')
    ducheng_qs = DuchengProblem.objects.filter(knowledgePoint2=kp2).order_by('-ducheng_id')
    all_courses = ClassName.objects.all()
    return render(request, 'quiz/teacher_kp_questions.html', {'title': '%s - 题目列表' % kp2.name, 'position': 'quiz_teacher_kp_manage', 'kp2': kp2, 'choice_questions': choice_qs, 'ducheng_questions': ducheng_qs, 'all_courses': all_courses})
