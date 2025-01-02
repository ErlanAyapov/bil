from django.db import models

# Create your models here.
class Chapter(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    date = models.DateField()

class Section(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    content = models.TextField()

class Question(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    text = models.TextField()
    difficulty = models.CharField(max_length=50, choices=[('easy', 'Оңай"'), ('medium', 'Орташа'), ('hard', 'Қиын')])

class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    text = models.CharField(max_length=200)
    is_correct = models.BooleanField(default=False)

class Result(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, null=True, blank=True)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.ForeignKey(Option, on_delete=models.CASCADE)
    is_correct = models.BooleanField()

    def save(self, *args, **kwargs):
        if self.pk is None:
            # Автоматическое заполнение поля is_correct
            self.is_correct = self.selected_option.is_correct
        super().save(*args, **kwargs)


class Progress(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    is_completed = models.BooleanField(default=False)
    date = models.DateField(auto_now_add=True)
    score = models.IntegerField(default=0)
