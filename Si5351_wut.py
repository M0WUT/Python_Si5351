import math
import Adafruit_I2C

Si5351_I2C_ADDRESS = 0x60

#Register Addresses
Si5351_OUTPUT_ENABLE_REG = 3
Si5351_CLK0_CONTROL_REG = 16
Si5351_XTAL_REG = 183
Si5351_PLL_A_CONTROL_REG = 22
Si5351_PLL_A_MULTIPLIER_REG = 26
Si5351_CLK0_DIVIDER_REG = 42
Si5351_CLK0_CONFIG_REG = 16

#Useful Values
Si5351_ALL_OUTPUTS_DISABLED = 0xFF
Si5351_CLOCK_POWERED_DOWN = 0x80
Si5351_XTAL_6pF = (1<<6)
Si5351_XTAL_8pF = (2<<6)
Si5351_XTAL_10pF = (3<<6)
Si5351_XTAL_REG_LOWER_BITS = 0b010010
Si5351_PLL_INTEGER_MODE = (1<<6)

class Si5351_wut(object):
	
	def __init__(self, xtal_capacitance, xtal_frequency):
		self.plla_frequency = 0
		self.pllb_frequency = 0
		self.xtal_frequency = xtal_frequency
		self.xtal_capacitance = xtal_capacitance
		self.i2c = Adafruit_I2C(Si5351_I2C_ADDRESS)
		
		#Turn all outputs off
		self.i2c.write8(Si5351_OUTPUT_ENABLE_REG, Si5351_ALL_OUTPUTS_DISABLED)
		
		#Power down all 8 clocks
		self.i2c.writeList(Si5351_CLK0_CONTROL_REG, [Si5351_CLOCK_POWERED_DOWN] * 8)
		
		#Set Crystal Capacitance
		if xtal_capacitance == "XTAL_6pF":
			self.i2c.write8(Si5351_XTAL_REG, Si5351_XTAL_6PF | Si5351_XTAL_REG_LOWER_BITS)
			pass
		elif xtal_capacitance == "XTAL_8pF":
			self.i2c.write8(Si5351_XTAL_REG, Si5351_XTAL_8PF | Si5351_XTAL_REG_LOWER_BITS)
			pass
		elif xtal_capacitance == "XTAL_10pF":
			self.i2c.write8(Si5351_XTAL_REG, Si5351_XTAL_10PF | Si5351_XTAL_REG_LOWER_BITS)
			pass
		else:
			raise Exception("Specify crystal capacitance as \"XTAL_6pF\", \"XTAL_8pF\" or \"XTAL_10pF\"")
			
		#Sanity check crystal frequency (must be between 10MHz and 40MHz, recommended 25MHz or 27MHz)
		if( xtal_frequency < 10e6 or xtal_frequency > 40e6):
			raise Exception("Crystal frequency must be between 10MHz and 40MHz, specified in Hz")
			
		
	def disable_clock(self, clock):
		if(clock > 7):
			raise Exception("Attempted to access clock with a value of {:s}, this does not exist".format(clock))
		#x = self.i2c.readU8(Si5351_OUTPUT_ENABLE_REG)
		self.i2c.write8(Si5351_OUTPUT_ENABLE_REG, x | (1<<clock))
		
	
	def set_PLL(self, pll, target_frequency):
	
		if(target_frequency < 600e6 or target_frequency > 900e6):
			raise Exception("Target PLL frequency must be between 600MHz and 900MHz (specified in Hz)")
	
		if pll == "PLL_A":
			pll_value = 0
		elif pll == "PLL_B":
			pll_value = 1
		else:
			raise Exception("PLL must be specified as either \"PLL_A\" or \"PLL_B\"")
			
		#get multiplier values a, b and c. PLL_frequency = Xtal_frequency * (a+b/c)
		a = math.floor(target_frequency / self.xtal_frequency)
		remainder = target_frequency - (self.xtal_frequency * a)
		remainder /= self.xtal_frequency
		b,c = self.__fraction_solve(remainder)
		if b==0 and (a%2) == 0:
			self.i2c.write8(Si5351_PLL_A_CONTROL_REG+pll_value, Si5351_PLL_INTEGER_MODE) #if integer division, enabling Integer mode lowers phase noise
			pass
			
		#Calculate actual output frequency
		actual_pll_frequency = self.xtal_frequency * (a+b/c)
		
		#ensure result is within 10Hz of target (not had any problems achieving this so far)
		if(abs(target_frequency - actual_pll_frequency) > 10):
			raise Exception("Unable to set {} to frequency {} within tolerance, best effort was {}".format(pll, target_frequency, actual_pll_frequency))
			
		#ensure multipliers are within valid range
		multiplier = a+b/c
		if multiplier<15 or multiplier > 90:
			raise Exception("Setting {} to {} with a crystal frequency of {} produced invalid multiplier of {}, multiplier (m) must satisfy 15<m<=90".format(pll, target_frequency, self.xtal_frequency, multiplier))
			
		#bit packing into registers, naming convention is crap but is consistent with Silicon Labs AN619 which specifies how to do this
		
		intermediate = math.floor(128*b/c) #value that gets used a couple of times
		
		p1 = math.floor(128*a + intermediate - 512)
		p2 = math.floor(128*b - c*intermediate)
		p3 = math.floor(intermediate)
		
		tx_buffer = [0]*8 #Blank list with 8 elements, not sure if this is the nicest way to do this next bit, I'm not a Python guy
		tx_buffer[0] = (p3>>8)&0xFF
		tx_buffer[1] = (p3&0xFF)
		tx_buffer[2] = (p1>>16)&0x03
		tx_buffer[3] = (p1>>8)&0xFF
		tx_buffer[4] = (p1&0xFF)
		tx_buffer[5] = ((p3>>12)&0xF0)|((p2>>16)&0x0F)
		tx_buffer[6] = (p2>>8)&0xFF
		tx_buffer[7] = (p2&0xFF)
		
		#Eight registers for PLL A multipliers, immediately followed by 8 for PLL B multipliers
		self.i2c.writeList(Si5351_PLL_A_MULTIPLIER_REG + (8*pll_value), tx_buffer)
		
		if(pll == "PLL_A"):
			self.plla_frequency = actual_pll_frequency
		else:
			self.pllb_frequency = actual_pll_frequency
			
		print("{} set to {}Hz".format(pll,actual_pll_frequency))
		
		
	def set_freq(self, clock, pll, target_frequency):
		if pll == "PLL_A":
			pll_value = 0
			pll_frequency = self.plla_frequency
		elif pll == "PLL_B":
			pll_value = 1
			pll_frequency = self.pllb_frequency
		else: 
			raise Exception("PLL must be specified as either \"PLL_A\" or \"PLL_B\"")
			
		if(clock > 2):
			raise Exception("Clock must be in range 0-7 (inclusive)")
			
		a = math.floor(pll_frequency / target_frequency)
		
		remainder = pll_frequency - (target_frequency * a)
		remainder /= target_frequency
		
		b,c = self.__fraction_solve(remainder)
		
		divider = a + b/c
		
		if divider < 6 or divider >1800:
			raise Exception("Target frequency frequency produced invalid divider for the PLL frequency chosen")
			
		actual_output_frequency = pll_frequency / divider
		
		intermediate = math.floor(128*b/c) #value that gets used a couple of times
		
		p1 = math.floor(128*a + intermediate - 512)
		p2 = math.floor(128*b - c*intermediate)
		p3 = math.floor(intermediate)
		
		tx_buffer = [0]*8 #Blank list with 8 elements, not sure if this is the nicest way to do this next bit, I'm not a Python guy
		tx_buffer[0] = (p3>>8)&0xFF
		tx_buffer[1] = (p3&0xFF)
		tx_buffer[2] = (p1>>16)&0x03
		tx_buffer[3] = (p1>>8)&0xFF
		tx_buffer[4] = (p1&0xFF)
		tx_buffer[5] = ((p3>>12)&0xF0)|((p2>>16)&0x0F)
		tx_buffer[6] = (p2>>8)&0xFF
		tx_buffer[7] = (p2&0xFF)
		
		#Eight registers for each clock 
		self.i2c.writeList(Si5351_CLK0_DIVIDER_REG + (8*clock), tx_buffer)
		
		#Check for integer mode for that clock
		if b==0 and (a%2) == 0:
			int_mode = 1
		else:
			int_mode = 0
		
		#Write clock configuration
		self.i2c.write8(Si5351_CLK0_CONFIG_REG, (int_mode<<6) | (pll_value<<5) | 0x0F)
		
		#Enable clock
		reg = 0 #done so if I comment out I2C writes, reg still exists
		#reg = self.i2c.readU8(Si5351_OUTPUT_ENABLE_REG)
		reg &= (1<<clock) #clearing the corresponding bit enables the output
		self.i2c.write8(Si5351_OUTPUT_ENABLE_REG, reg)
		
		print("Clock {} set to {}Hz".format(clock, actual_output_frequency))
		
		
		
		
	
	def __fraction_solve(self, x0): #Return numerator and denominator for best expression for the decimal x0 (0<x0<1)
		if(x0 < 0 or x0 > 1):
			raise Exception("Decimal supplied (x) must satisfy 0 < x < 1") 
		err = 1e-10
		g = abs(x0)
		a = 0.0
		b = 1.0
		c = 1.0
		d = 0.0
		s = 0.0
		iter = 0
		
		while iter < 1000:
			s = math.floor(g)
			num = a + s*c
			den = b + s*d
			a = c
			b = d
			c = num
			d = den
			try:
				g = 1.0/(g-s)
			except ZeroDivisionError: #g=s at very very close solutions so will terminate next time
				g=g
			if(err > abs((num/den) - x0)):
				if(b>1048575 or c>1048575):
					raise Exception("Produced values for fraction out of specified range")
				return (num, den)
			iter += 1
		
		#Have tried a thousand times, give up (most values this was run on returned within 20 iterations
		raise Exception("Could not find adequate results to express {:f} as a fraction".format(x0))
		
if __name__ == '__main__':
	a=Si5351_wut("XTAL_10pF",25e6)
	a.set_PLL("PLL_A", 800e6)
	a.set_PLL("PLL_B", 600e6)
	a.set_freq(0, "PLL_A", 3.6e6)
	a.set_freq(1, "PLL_A", 14.07e6)
	a.set_freq(2, "PLL_B", 28e6)
	

				
