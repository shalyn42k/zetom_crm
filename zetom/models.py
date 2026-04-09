from django.db import models
from django import forms
from django.core.validators import RegexValidator

from phonenumber_field.modelfields import PhoneNumberField

class Request_Null(models.Model):
	created_at = models.DateTimeField(auto_now_add=True)
	phone = PhoneNumberField(blank=False)
	company_name = models.CharField(max_length=50, blank=True)
	email = models.EmailField(
		max_length=100,
		validators=[
			
		]
	)
	company_nip = models.CharField(
		max_length=10,
		validators=[
			RegexValidator(
				regex=r'^[0-9-]+$',
				message="Your NIP sucks man, It must be 10 digits yo"
			)
		],
		blank=True
	)
	
	def __str__(self):
	    return(f"{self.company_name}")

#class Oferta(models.Model):
#	created_at = models.DateTimeField(auto_now_add=True)
#	phone = PhoneNumberField(blank=True)
#	company_name = models.CharField(max_length=50, blank=False)
#	email = models.EmailField(max_length=500, blank=False)




